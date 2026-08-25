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


def _safe_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        raise PackageValidationError("The archive contains an invalid empty path.")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise PackageValidationError("Unsafe archive path: {0}".format(name))
    if path.parts and ":" in path.parts[0]:
        raise PackageValidationError("Unsafe archive path: {0}".format(name))
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
