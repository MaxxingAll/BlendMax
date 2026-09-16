"""Secure, selective extraction of a .blendmax archive."""

from __future__ import annotations

import json
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Dict, Iterator

from .errors import ManifestValidationError, PackageValidationError
from .manifest import parse_manifest
from .models import PackageContents


MAX_ARCHIVE_ENTRIES = 2048
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024


# Names the Windows kernel resolves to a device rather than a file, whatever
# the extension: "CON.txt" is still the console. Compared case-insensitively
# against the part before the first dot.
#
# This is a static list, NOT a probe of the current machine. The devices a
# given host actually exposes vary (a build machine may have COM1, a laptop
# none), but a package must not be able to name a device on whichever host
# later extracts it. COM0/LPT0 are deliberately excluded: Windows documents
# COM1-COM9 and LPT1-LPT9, and COM10 is explicitly NOT reserved.
#
# Microsoft also reserves the ISO/IEC 8859-1 superscript digits as parts of
# COM#/LPT# device names: "Windows recognizes the 8-bit ISO/IEC 8859-1
# superscript digits [U+00B9], [U+00B2], and [U+00B3] as digits and treats
# them as valid parts of COM# and LPT# device names, making them reserved in
# every directory." So COM<U+00B9> is a device name exactly as COM1 is.
# Only those three 8859-1 code points are named by the documentation; the
# Unicode superscripts block (U+2070-U+2079) is NOT documented as reserved
# and is deliberately not included.
_WINDOWS_RESERVED_NAMES = frozenset(
    [
        "con",
        "prn",
        "aux",
        "nul",
        "conin$",
        "conout$",
    ]
    + ["com{0}".format(index) for index in range(1, 10)]
    + ["lpt{0}".format(index) for index in range(1, 10)]
    # Escapes rather than literal glyphs, so the code points are unambiguous
    # and survive copy/paste: \u00b9 = superscript one, \u00b2 = two,
    # \u00b3 = three.
    + ["com\u00b9", "com\u00b2", "com\u00b3"]
    + ["lpt\u00b9", "lpt\u00b2", "lpt\u00b3"]
)


def _windows_hazard(part: str) -> str:
    """Describe why ``part`` is unsafe as a Windows path component, else ""."""

    # Windows silently strips a trailing dot or space when creating a name,
    # so "report." and "report" are the same file: two archive entries can
    # collide and one silently overwrites the other.
    if part != part.rstrip(". "):
        return "trailing dot or space"
    # A colon introduces an NTFS alternate data stream or a device reference
    # ("file.txt:ads"), and a drive-relative prefix ("C:file") resolves
    # outside the destination on Windows.
    if ":" in part:
        return "colon is not allowed in a path component"
    stem = part.split(".", 1)[0].casefold()
    if stem in _WINDOWS_RESERVED_NAMES:
        return "reserved Windows device name"
    return ""


def _safe_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        raise PackageValidationError("The archive contains an invalid empty path.")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise PackageValidationError("Unsafe archive path: {0}".format(name))
    # Every component is checked, not just the basename: a hazard in a middle
    # directory ("dir/CON/file.txt") is extracted just the same.
    for part in path.parts:
        hazard = _windows_hazard(part)
        if hazard:
            raise PackageValidationError(
                "Unsafe archive path: component {0!r} in {1} {2}".format(
                    part, name, hazard
                )
            )
    cleaned = path.as_posix()
    if cleaned in {"", "."}:
        raise PackageValidationError("Unsafe archive path: {0}".format(name))
    return cleaned


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _validated_members(archive: zipfile.ZipFile) -> Dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise PackageValidationError("The archive contains too many entries.")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        raise PackageValidationError("The archive expands beyond the 16 GiB safety limit.")

    members: Dict[str, zipfile.ZipInfo] = {}
    folded_names = set()
    for info in infos:
        name = _safe_name(info.filename)
        if _is_symlink(info):
            raise PackageValidationError("Archive links are not supported: {0}".format(name))
        if info.is_dir():
            continue
        folded = name.casefold()
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
