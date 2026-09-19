"""Secure, selective extraction of a .blendmax archive."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Dict, Iterator

from .errors import ManifestValidationError, PackageValidationError
from .manifest import parse_manifest
from .models import PackageContents

try:
    # Built extension: tools/build_blender_extension.py copies the shared policy
    # to the archive root, which is this package's root, so it is a sibling.
    from . import blendmax_archive_policy as archive_policy
except ImportError:  # pragma: no cover - exercised by the source-tree checkout
    # Source tree and tests: the canonical file lives at the repository root.
    import blendmax_archive_policy as archive_policy


# Bound here rather than read through archive_policy at each call site, so the
# limits stay patchable in this module -- the tests lower them to exercise the
# boundary without building a 16 GiB archive.
MAX_ARCHIVE_ENTRIES = archive_policy.MAX_ARCHIVE_ENTRIES
MAX_UNCOMPRESSED_BYTES = archive_policy.MAX_UNCOMPRESSED_BYTES


def _safe_name(name: str) -> str:
    """Return the normalized member path, raising for an unsafe one.

    The rules themselves live in :mod:`blendmax_archive_policy`; this stays a
    thin adapter so the consumer keeps its own exception type and message
    wording. Nothing in the shared module raises or knows about
    ``PackageValidationError``.
    """

    result = archive_policy.check_member_path(name)
    if result.reason == archive_policy.REASON_EMPTY:
        raise PackageValidationError("The archive contains an invalid empty path.")
    if result.reason == archive_policy.REASON_COMPONENT:
        # Every component is checked, not just the basename: a hazard in a
        # middle directory ("dir/CON/file.txt") is extracted just the same.
        raise PackageValidationError(
            "Unsafe archive path: component {0!r} in {1} {2}".format(
                result.part, name, result.hazard
            )
        )
    if result.reason:
        # Absolute paths and ".." traversal both land on the generic message.
        raise PackageValidationError("Unsafe archive path: {0}".format(name))
    return result.cleaned


def _validated_members(archive: zipfile.ZipFile) -> Dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise PackageValidationError("The archive contains too many entries.")
    if archive_policy.declared_uncompressed_bytes(infos) > MAX_UNCOMPRESSED_BYTES:
        raise PackageValidationError("The archive expands beyond the 16 GiB safety limit.")

    members: Dict[str, zipfile.ZipInfo] = {}
    folded_names = set()
    for info in infos:
        name = _safe_name(info.filename)
        if archive_policy.is_symlink(info):
            raise PackageValidationError("Archive links are not supported: {0}".format(name))
        if info.is_dir():
            continue
        # Duplicate detection stays interleaved with the other per-member
        # checks so that the reported error is the first one in archive order;
        # the folding rule itself is shared.
        folded = archive_policy.folded_path(name)
        if folded in folded_names:
            raise PackageValidationError("Duplicate archive path: {0}".format(name))
        folded_names.add(folded)
        members[name] = info
    return members


def _read_manifest(archive: zipfile.ZipFile, members: Dict[str, zipfile.ZipInfo]):
    info = members.get("manifest.json")
    if info is None:
        raise PackageValidationError("The package does not contain manifest.json.")
    try:
        raw = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestValidationError("Could not decode manifest.json: {0}".format(exc)) from exc
    return parse_manifest(raw)


def _extract_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
) -> Path:
    target = destination.joinpath(*PurePosixPath(_safe_name(info.filename)).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info, "r") as source, target.open("wb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
    return target


@contextmanager
def open_blendmax(path) -> Iterator[PackageContents]:
    source_path = Path(path).expanduser().resolve()
    if source_path.suffix.casefold() != ".blendmax":
        raise PackageValidationError("Select a file with the .blendmax extension.")
    if not source_path.is_file():
        raise PackageValidationError("BlendMax package not found: {0}".format(source_path))

    try:
        archive = zipfile.ZipFile(source_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageValidationError("Could not open the BlendMax package: {0}".format(exc)) from exc

    with archive:
        members = _validated_members(archive)
        manifest = _read_manifest(archive, members)
        geometry_name = _safe_name(manifest.geometry_file)
        geometry_info = members.get(geometry_name)
        if geometry_info is None:
            raise PackageValidationError(
                "The package does not contain {0}.".format(manifest.geometry_file)
            )

        texture_infos: Dict[str, zipfile.ZipInfo] = {}
        for record in manifest.textures:
            if record.status != "copied" or not record.package_path:
                continue
            member_name = _safe_name(record.package_path)
            info = members.get(member_name)
            if info is None:
                raise PackageValidationError(
                    "Packaged texture is missing: {0}.".format(record.package_path)
                )
            texture_infos[member_name] = info

        with tempfile.TemporaryDirectory(prefix="blendmax_import_") as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.raw, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            geometry_path = _extract_member(archive, geometry_info, root)
            texture_paths = {
                member_name: _extract_member(archive, info, root)
                for member_name, info in texture_infos.items()
            }
            yield PackageContents(
                source_path=source_path,
                root=root,
                geometry_path=geometry_path,
                manifest=manifest,
                texture_paths=texture_paths,
            )
