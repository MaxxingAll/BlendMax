"""Shared archive path and security policy for the BlendMax artifacts.

This module is the single source of truth for the archive rules that the Blender
``.blendmax`` importer and the 3ds Max update-ZIP installer must both enforce.
It is deliberately dependency-light: standard library only, and it imports
neither deployment package, so it can be dropped into either artifact.

WHY IT LIVES AT THE REPOSITORY ROOT
    The two shipped artifacts are disjoint. The Blender extension contains only
    ``blendmax_blender/`` (its build flattens that directory to the archive root,
    which becomes the import package). The 3ds Max bundle contains only
    ``Contents/python/{blendmax_max, blendmax_install.py}``. Neither can import
    the other at runtime, so shared code has to live somewhere neutral and be
    copied into both by their own build recipes -- see
    ``tools/build_blender_extension.py``, ``tools/build_release.py`` and
    ``build_bundle()`` in ``blendmax_install.py``.

CONTRACT
    Nothing here raises, and nothing here knows about either caller's exception
    type or message wording. Callers get a reason back and compose their own
    errors, which is what keeps the two consumers' user-facing behaviour their
    own. This module decides *what is unsafe*; callers decide how to say it.
"""

from __future__ import annotations

import stat
import zipfile
from pathlib import PurePosixPath
from typing import Iterable, NamedTuple, Optional

# Enforced by both consumers before anything touches the disk. These used to be
# duplicated in blendmax_blender/package.py and blendmax_install.py with a drift
# guard test holding them equal; they are shared here instead.
MAX_ARCHIVE_ENTRIES = 2048
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024

# Member-path rejection reasons. Short machine-readable kinds, so each caller can
# map them to its own wording.
REASON_EMPTY = "empty"
REASON_ABSOLUTE = "absolute"
REASON_TRAVERSAL = "traversal"
REASON_COMPONENT = "component"

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
WINDOWS_RESERVED_NAMES = frozenset(
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


class MemberPath(NamedTuple):
    """Result of checking one archive member name.

    ``reason`` is empty when the name is safe, in which case ``cleaned`` holds
    the normalized path. When a reason is set, ``cleaned`` is empty and the
    offending component is in ``part`` with a human-readable ``hazard``.
    """

    cleaned: str
    reason: str
    part: str = ""
    hazard: str = ""


def windows_hazard(part: str) -> str:
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
    if stem in WINDOWS_RESERVED_NAMES:
        return "reserved Windows device name"
    return ""


def check_member_path(name: str) -> MemberPath:
    """Normalize ``name`` and report the first reason it is unsafe.

    Backslashes are treated as separators, because an archive written on
    Windows may use them and a consumer that only recognizes forward slashes
    would miss a hazard. Every component is checked, not just the basename: a
    hazard in a middle directory ("dir/CON/file.txt") is extracted just the same.
    """

    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        return MemberPath("", REASON_EMPTY)
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return MemberPath("", REASON_ABSOLUTE)
    if ".." in path.parts:
        return MemberPath("", REASON_TRAVERSAL)
    for part in path.parts:
        hazard = windows_hazard(part)
        if hazard:
            return MemberPath("", REASON_COMPONENT, part, hazard)
    cleaned = path.as_posix()
    if cleaned in {"", "."}:
        return MemberPath("", REASON_EMPTY)
    return MemberPath(cleaned, "")


def is_symlink(info: zipfile.ZipInfo) -> bool:
    """True when the entry is a symbolic link rather than a regular file."""

    return stat.S_ISLNK(info.external_attr >> 16)


def folded_path(cleaned: str) -> str:
    """The key used for duplicate detection: paths collide case-insensitively.

    Windows and macOS treat ``Readme.md`` and ``README.MD`` as the same file, so
    an archive carrying both would have one entry silently overwrite the other.
    """

    return cleaned.casefold()


def first_duplicate(names: Iterable[str]) -> Optional[str]:
    """Return the second spelling of the first case-insensitively repeated path.

    ``names`` must already be cleaned paths. Returns ``None`` when every path is
    distinct under :func:`folded_path`.
    """

    seen = set()
    for name in names:
        folded = folded_path(name)
        if folded in seen:
            return name
        seen.add(folded)
    return None


def declared_uncompressed_bytes(infos: Iterable[zipfile.ZipInfo]) -> int:
    """Total bytes the members declare they expand to.

    Directory entries declare no bytes, so counting them here changes nothing --
    but they do count towards :data:`MAX_ARCHIVE_ENTRIES`.
    """

    return sum(info.file_size for info in infos)
