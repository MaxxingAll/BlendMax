"""Build and install the per-user BlendMax 3ds Max AppBundle."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Mapping, Optional


BUNDLE_NAME = "BlendMax.bundle"
TEMPLATE_RELATIVE = Path("appbundle") / BUNDLE_NAME
CORE_PACKAGE_RELATIVE = Path("blendmax_max")
VERSION_FILE_RELATIVE = CORE_PACKAGE_RELATIVE / "__init__.py"
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


class InstallError(RuntimeError):
    """Raised when an install or update package is invalid."""


def default_install_root(
    environ: Optional[Mapping[str, str]] = None,
) -> Path:
    values = os.environ if environ is None else environ
    appdata = values.get("APPDATA")
    if not appdata:
        raise InstallError("Windows APPDATA is unavailable; cannot locate ApplicationPlugins.")
    return Path(appdata) / "Autodesk" / "ApplicationPlugins"


def source_version(source_root: Path) -> str:
    version_file = Path(source_root) / VERSION_FILE_RELATIVE
    try:
        contents = version_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallError("BlendMax version file is missing: {0}".format(exc))
    match = VERSION_PATTERN.search(contents)
    if not match:
        raise InstallError("BlendMax version could not be read from {0}.".format(version_file))
    return match.group(1)


def validate_source_root(source_root: Path) -> str:
    root = Path(source_root).resolve()
    required = (
        root / VERSION_FILE_RELATIVE,
        root / "blendmax_install.py",
        root / TEMPLATE_RELATIVE / "PackageContents.xml",
        root / TEMPLATE_RELATIVE / "Contents" / "macroscripts" / "BlendMax.mcr",
        root
        / TEMPLATE_RELATIVE
        / "Contents"
        / "Post-Start-Up_Scripts"
        / "BlendMaxMenu2025.ms",
        root
        / TEMPLATE_RELATIVE
        / "Contents"
        / "python"
        / "blendmax_actions.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise InstallError(
            "This is not a complete BlendMax release. Missing:\n{0}".format(
                "\n".join(missing)
            )
        )
    return source_version(root)


def build_bundle(source_root: Path, destination_bundle: Path) -> str:
    source = Path(source_root).resolve()
    destination = Path(destination_bundle)
    version = validate_source_root(source)
    if destination.exists():
        raise InstallError("Bundle staging destination already exists: {0}".format(destination))

    try:
        shutil.copytree(
            source / TEMPLATE_RELATIVE,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        python_root = destination / "Contents" / "python"
        shutil.copytree(
            source / CORE_PACKAGE_RELATIVE,
            python_root / CORE_PACKAGE_RELATIVE,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        shutil.copy2(source / "blendmax_install.py", python_root / "blendmax_install.py")
    except OSError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise InstallError("Could not build BlendMax.bundle: {0}".format(exc))
    return version


def install_from_source(
    source_root: Path,
    install_root: Optional[Path] = None,
) -> Dict[str, str]:
    plugins_root = (
        default_install_root() if install_root is None else Path(install_root).resolve()
    )
    plugins_root.mkdir(parents=True, exist_ok=True)

    transaction = uuid.uuid4().hex
    target = plugins_root / BUNDLE_NAME
    stage = plugins_root / (".{0}.stage-{1}".format(BUNDLE_NAME, transaction))
    backup = plugins_root / (".{0}.backup-{1}".format(BUNDLE_NAME, transaction))
    version = build_bundle(Path(source_root), stage)
    backup_created = False

    try:
        if target.exists():
            target.rename(backup)
            backup_created = True
        stage.rename(target)
    except OSError as exc:
        if target.exists() and backup_created:
            shutil.rmtree(target, ignore_errors=True)
        if backup_created and backup.exists() and not target.exists():
            backup.rename(target)
        shutil.rmtree(stage, ignore_errors=True)
        raise InstallError(
            "BlendMax installation failed; previous version restored: {0}".format(exc)
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)

    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)

    return {
        "version": version,
        "bundle_path": str(target),
    }


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute():
            raise InstallError("Update ZIP contains an absolute path: {0}".format(member.filename))
        unix_mode = member.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise InstallError("Update ZIP contains a symbolic link: {0}".format(member.filename))
        resolved = (root / member_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise InstallError("Update ZIP contains an unsafe path: {0}".format(member.filename))
    archive.extractall(root)


def find_source_root(extracted_root: Path) -> Path:
    root = Path(extracted_root).resolve()
    candidates = []
    direct = root / "install_blendmax.py"
    if direct.is_file():
        candidates.append(root)
    for installer in root.rglob("install_blendmax.py"):
        candidate = installer.parent.resolve()
        if candidate not in candidates:
            candidates.append(candidate)

    valid = []
    for candidate in candidates:
        try:
            validate_source_root(candidate)
            valid.append(candidate)
        except InstallError:
            continue
    if len(valid) != 1:
        raise InstallError(
            "Update ZIP must contain exactly one complete BlendMax release; found {0}.".format(
                len(valid)
            )
        )
    return valid[0]


def install_from_zip(
    archive_path: Path,
    install_root: Optional[Path] = None,
) -> Dict[str, str]:
    archive_file = Path(archive_path).resolve()
    if not archive_file.is_file() or archive_file.suffix.casefold() != ".zip":
        raise InstallError("Choose a BlendMax release ZIP file.")

    try:
        with tempfile.TemporaryDirectory(prefix="blendmax-update-") as temporary:
            extracted = Path(temporary)
            with zipfile.ZipFile(archive_file, "r") as archive:
                _safe_extract(archive, extracted)
            source_root = find_source_root(extracted)
            result = install_from_source(source_root, install_root=install_root)
    except zipfile.BadZipFile as exc:
        raise InstallError("The selected update is not a valid ZIP file: {0}".format(exc))

    result["archive_path"] = str(archive_file)
    return result
