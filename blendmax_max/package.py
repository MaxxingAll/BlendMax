"""Build the portable .blendmax ZIP container."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List


def ensure_blendmax_suffix(path) -> Path:
    output = Path(path)
    if output.suffix.lower() != ".blendmax":
        output = output.with_name(output.name + ".blendmax")
    return output


def write_manifest(path, manifest: Dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _unique_texture_name(source: Path, used_names: Dict[str, Path]) -> str:
    candidate = source.name
    key = candidate.casefold()
    if key not in used_names:
        used_names[key] = source
        return candidate
    if used_names[key] == source:
        return candidate

    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:8]
    candidate = "{0}_{1}{2}".format(source.stem, digest, source.suffix)
    used_names[candidate.casefold()] = source
    return candidate


def copy_texture_files(
    source_paths: Iterable[str],
    texture_directory,
) -> List[Dict[str, Any]]:
    destination = Path(texture_directory)
    destination.mkdir(parents=True, exist_ok=True)
    used_names: Dict[str, Path] = {}
    records: List[Dict[str, Any]] = []
    seen_sources = set()

    for raw_path in source_paths:
        raw = str(raw_path or "").strip()
        if not raw or raw.casefold() in {"none", "undefined"}:
            continue
        source = Path(os.path.expandvars(raw)).expanduser()
        source_key = os.path.normcase(os.path.abspath(str(source)))
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        record: Dict[str, Any] = {
            "source_path": raw,
            "status": "missing",
            "package_path": None,
        }
        if source.is_file():
            filename = _unique_texture_name(source, used_names)
            target = destination / filename
            if not target.exists():
                shutil.copy2(str(source), str(target))
            record["status"] = "copied"
            record["package_path"] = "textures/{0}".format(filename)
        records.append(record)

    return records


def create_archive(source_directory, output_path) -> Path:
    source = Path(source_directory)
    output = ensure_blendmax_suffix(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")

    try:
        with zipfile.ZipFile(
            str(temporary),
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(str(path), path.relative_to(source).as_posix())
        os.replace(str(temporary), str(output))
    finally:
        if temporary.exists():
            temporary.unlink()

    return output
