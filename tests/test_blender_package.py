from __future__ import annotations

import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from blendmax_blender import package as blender_package
from blendmax_blender.errors import PackageValidationError
from blendmax_blender.package import (
    MAX_ARCHIVE_ENTRIES,
    _safe_name,
    open_blendmax,
)
from fakes import _InflatingStream, _PumpingStream, _stream_for
from test_blender_manifest import valid_manifest


def write_package(path: Path, manifest=None, extra=None):
    manifest = manifest or valid_manifest()
    extra = extra or {}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("geometry.fbx", b"fbx")
        archive.writestr("textures/wood.png", b"image")
        for name, contents in extra.items():
            archive.writestr(name, contents)


class BlenderPackageTests(unittest.TestCase):
    def test_extracts_only_declared_import_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Chair.blendmax"
            write_package(path, extra={"notes.txt": b"not imported"})

            with open_blendmax(path) as package:
                self.assertEqual(package.geometry_path.read_bytes(), b"fbx")
                self.assertEqual(
                    package.texture_paths["textures/wood.png"].read_bytes(),
                    b"image",
                )
                self.assertFalse((package.root / "notes.txt").exists())

    def test_rejects_archive_traversal_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Unsafe.blendmax"
            write_package(path, extra={"../escape.txt": b"bad"})
            with self.assertRaisesRegex(PackageValidationError, "Unsafe archive path"):
                with open_blendmax(path):
                    pass

    def test_rejects_missing_declared_texture(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Missing.blendmax"
            raw = valid_manifest()
            raw["textures"][0]["package_path"] = "textures/missing.png"
            write_package(path, raw)
            with self.assertRaisesRegex(PackageValidationError, "texture is missing"):
                with open_blendmax(path):
                    pass

    def test_rejects_wrong_file_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Chair.zip"
            write_package(path)
            with self.assertRaisesRegex(PackageValidationError, r"\.blendmax"):
                with open_blendmax(path):
                    pass


class ArchiveFilenameHardeningTests(unittest.TestCase):
    """Windows path-component hazards in archive member names.

    Windows resolves some names to devices rather than files, strips trailing
    dots and spaces, and treats a colon as an alternate-data-stream or
    drive-relative marker. A member name carrying any of those can escape the
    destination or collide with another entry, so each component is validated
    rather than only the basename.

    The hazard set is a static name list, not a probe of the extracting host:
    which devices exist varies per machine, but a package must not be able to
    name a device on whichever host later opens it.
    """

    def _rejects(self, name, pattern):
        with self.assertRaisesRegex(PackageValidationError, pattern, msg=name):
            _safe_name(name)

    def _accepts(self, name):
        return _safe_name(name)

    # --- reserved device names -------------------------------------------

    def test_rejects_reserved_device_names(self):
        for name in ("CON", "PRN", "AUX", "NUL"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_numbered_reserved_device_names(self):
        for prefix in ("COM", "LPT"):
            for index in range(1, 10):
                name = "{0}{1}".format(prefix, index)
                with self.subTest(name=name):
                    self._rejects(name, "reserved Windows device name")

    def test_reserved_device_names_are_case_insensitive(self):
        for name in ("con", "Con", "cOn", "nul", "NuL", "prn", "aux"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_reserved_device_name_with_extension_is_still_reserved(self):
        """The kernel resolves the device whatever the extension: CON.txt is
        the console, so an extension must not be an escape hatch."""
        for name in ("CON.txt", "con.TXT", "NUL.tar.gz", "COM1.fbx", "lpt9.png"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_console_io_devices(self):
        for name in ("CONIN$", "CONOUT$"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    # --- hazards in a component that is not the basename ------------------

    def test_rejects_reserved_name_in_middle_component(self):
        """Every component is extracted, so a hazard in a directory is not
        safer than one in the filename."""
        for name in ("dir/CON", "CON/file.txt", "dir/AUX.txt", "a/b/NUL.txt"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_trailing_dot_in_middle_component(self):
        self._rejects("dir/name./file.txt", "trailing dot or space")

    def test_rejects_colon_in_middle_component(self):
        """The colon check used to cover only the first component, so
        'a/b:c' passed while 'C:/evil' was caught."""
        self._rejects("a/b:c", "colon is not allowed")

    # --- trailing dot or space -------------------------------------------

    def test_rejects_trailing_dot(self):
        for name in ("trailing.", "a.b.", "dir/name."):
            with self.subTest(name=name):
                self._rejects(name, "trailing dot or space")

    def test_rejects_trailing_space(self):
        for name in ("trailing ", "dir/name ", "two  spaces "):
            with self.subTest(name=name):
                self._rejects(name, "trailing dot or space")

    # --- colon: alternate data streams and drive-relative paths ----------

    def test_rejects_alternate_data_stream_syntax(self):
        for name in ("file.txt:ads", "dir:ads/file.txt", "dir/file.txt:stream"):
            with self.subTest(name=name):
                self._rejects(name, "colon is not allowed")

    def test_rejects_drive_relative_prefix(self):
        for name in ("C:evil", "C:/evil", "c:dir/file.txt"):
            with self.subTest(name=name):
                self._rejects(name, "colon is not allowed")

    # --- hazards must be rejected at open time, before extraction --------

    def test_rejects_hazardous_entry_before_extraction(self):
        for name in ("dir/CON.txt", "bad.", "bad:ads", "dir/bad "):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "Hazard.blendmax"
                    write_package(path, extra={name: b"x"})
                    with self.assertRaises(PackageValidationError):
                        with open_blendmax(path):
                            pass

    def test_rejects_hazardous_manifest_declared_path(self):
        """Manifest-declared paths go through the same validator."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Hazard.blendmax"
            raw = valid_manifest()
            raw["geometry"]["file"] = "CON.fbx"
            write_package(path, raw)
            with self.assertRaisesRegex(
                PackageValidationError, "reserved Windows device name"
            ):
                with open_blendmax(path):
                    pass

    # --- legitimate names must not be over-restricted --------------------

    def test_accepts_ordinary_names(self):
        for name in (
            "manifest.json",
            "geometry.fbx",
            "textures/wood.png",
            "my.asset.v2.fbx",
            "file with space.txt",
            "dir/sub/file.png",
            "-dash_and_underscore.txt",
            ".hidden",
            "file.name.ext",
        ):
            with self.subTest(name=name):
                self.assertEqual(self._accepts(name), name)

    def test_accepts_names_that_only_resemble_hazards(self):
        """Guards against over-restriction: a reserved PREFIX is fine, and
        only COM1-COM9/LPT1-LPT9 are reserved, so COM10 is a normal name."""
        for name in (
            "CONSOLE.txt",
            "conartist.txt",
            "nulled.txt",
            "auxiliary.png",
            "COM10.txt",
            "LPT10",
            "COM0",
            "LPT0",
            "CLOCK$",
            "printer.txt",
        ):
            with self.subTest(name=name):
                self.assertEqual(self._accepts(name), name)

    def test_interior_space_and_dot_are_allowed(self):
        """Only a TRAILING dot or space is a hazard."""
        for name in ("name with spaces.txt", "a.b.c.d", "sp ace mid.txt"):
            with self.subTest(name=name):
                self.assertEqual(self._accepts(name), name)

    def test_trailing_dot_with_interior_space_is_still_rejected(self):
        self._rejects("sp ace.", "trailing dot or space")

    def test_rejects_superscript_device_names(self):
        """Microsoft reserves the ISO/IEC 8859-1 superscript digits.

        "Windows recognizes the 8-bit ISO/IEC 8859-1 superscript digits
        [U+00B9], [U+00B2], and [U+00B3] as digits and treats them as valid
        parts of COM# and LPT# device names, making them reserved in every
        directory." Only those three code points are named.
        """

        for name in (
            "COM\u00b9", "COM\u00b2", "COM\u00b3",
            "LPT\u00b9", "LPT\u00b2", "LPT\u00b3",
        ):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_superscript_device_names_case_insensitively(self):
        for name in ("com\u00b9", "Com\u00b2", "lPt\u00b3", "LPT\u00b9"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_superscript_device_names_with_extension(self):
        for name in ("COM\u00b9.txt", "lpt\u00b2.fbx", "dir/COM\u00b3.png"):
            with self.subTest(name=name):
                self._rejects(name, "reserved Windows device name")

    def test_rejects_superscript_device_name_in_middle_component(self):
        self._rejects("COM\u00b9/file.txt", "reserved Windows device name")
        self._rejects("dir/LPT\u00b3/asset.fbx", "reserved Windows device name")

    def test_unicode_block_superscripts_are_not_reserved(self):
        """Only the ISO/IEC 8859-1 superscripts are documented as reserved.

        The Unicode superscripts block (U+2070-U+2079) is not named by
        Microsoft, so rejecting it would over-restrict. This pins the
        boundary of the change.
        """

        for name in ("COM\u2074", "COM\u2075", "LPT\u2079.txt"):
            with self.subTest(name=name):
                self.assertEqual(self._accepts(name), name)

    def test_accepts_superscripts_in_ordinary_names(self):
        """A superscript is only a hazard as part of a device name.

        Rejecting every name containing one would over-restrict legitimate
        textures and assets.
        """

        for name in ("caf\u00e9\u00b9.png", "x\u00b2.txt", "dir\u00b3/file.txt"):
            with self.subTest(name=name):
                self.assertEqual(self._accepts(name), name)


class ArchiveSecurityRegressionTests(unittest.TestCase):
    """Regression coverage for archive-security behaviour already enforced.

    These pin protections that were implemented but not covered by tests:
    traversal and absolute forms beyond a leading ``../``, symlink rejection in
    the package validator, case-insensitive duplicate detection, the
    package-side resource limits, and the no-write guarantee on refusal.

    The validator's Windows policy is static, so those cases are asserted
    against ``_safe_name`` rather than against host filesystem behaviour.
    """

    # How many members write_package() always adds: manifest.json,
    # geometry.fbx and textures/wood.png.
    FIXED_MEMBERS = 3

    # -- B. traversal and absolute paths ----------------------------------

    def test_rejects_traversal_and_absolute_names(self):
        for name in (
            "../file",
            "a/../../file",
            "..\\file",
            "a/..\\..\\file",
            "/tmp/file",
            "C:\\file",
            "C:file",
            "C:/file",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    PackageValidationError, "Unsafe archive path", msg=name
                ):
                    _safe_name(name)

    def test_rejects_traversal_entries_before_extraction(self):
        for name in ("../escape.txt", "a/../../escape.txt", "..\\escape.txt"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "Unsafe.blendmax"
                    write_package(path, extra={name: b"bad"})

                    yielded = False
                    with self.assertRaises(PackageValidationError):
                        with open_blendmax(path):
                            yielded = True

                    self.assertFalse(
                        yielded, "contents were yielded for {0}".format(name)
                    )

    # -- C. symlinks ------------------------------------------------------

    def test_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Link.blendmax"
            with zipfile.ZipFile(
                path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("manifest.json", json.dumps(valid_manifest()))
                archive.writestr("geometry.fbx", b"fbx")
                archive.writestr("textures/wood.png", b"image")
                info = zipfile.ZipInfo("link.txt")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "elsewhere.txt")

            yielded = False
            with self.assertRaisesRegex(
                PackageValidationError, "links are not supported"
            ):
                with open_blendmax(path):
                    yielded = True

            self.assertFalse(yielded)

    # -- D. duplicate archive names ---------------------------------------

    def test_rejects_case_insensitive_duplicate_entries(self):
        cases = (
            {"foo.txt": b"1", "FOO.TXT": b"2"},
            {"Textures/wood.png": b"1"},          # collides with textures/wood.png
            {"a/b/c.bin": b"1", "A/B/C.BIN": b"2"},
        )
        for extra in cases:
            with self.subTest(entry=sorted(extra)):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "Duplicate.blendmax"
                    write_package(path, extra=extra)

                    with self.assertRaisesRegex(
                        PackageValidationError, "Duplicate archive path"
                    ):
                        with open_blendmax(path):
                            pass

    # -- E. package resource limits ---------------------------------------

    def _write_with_extra_entries(self, path, extras):
        """Write a valid package plus ``extras`` filler members; return the
        real member count so a test can assert it rather than assume it."""
        write_package(
            path,
            extra={"f{0}.txt".format(index): b"x" for index in range(extras)},
        )
        with zipfile.ZipFile(path) as archive:
            return len(archive.infolist())

    def test_accepts_package_at_entry_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "AtLimit.blendmax"
            count = self._write_with_extra_entries(
                path, MAX_ARCHIVE_ENTRIES - self.FIXED_MEMBERS
            )
            self.assertEqual(count, MAX_ARCHIVE_ENTRIES)

            with open_blendmax(path):
                pass

    def test_rejects_package_above_entry_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "TooMany.blendmax"
            count = self._write_with_extra_entries(path, MAX_ARCHIVE_ENTRIES)
            self.assertGreater(count, MAX_ARCHIVE_ENTRIES)

            yielded = False
            with self.assertRaisesRegex(PackageValidationError, "too many entries"):
                with open_blendmax(path):
                    yielded = True

            self.assertFalse(yielded)

    def test_byte_budget_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Bytes.blendmax"
            write_package(path, extra={"blob.bin": b"x" * 1024})
            with zipfile.ZipFile(path) as archive:
                total = sum(info.file_size for info in archive.infolist())
            self.assertGreater(total, 1024)

            with mock.patch.object(
                blender_package, "MAX_UNCOMPRESSED_BYTES", total
            ):
                with open_blendmax(path):
                    pass

            yielded = False
            with mock.patch.object(
                blender_package, "MAX_UNCOMPRESSED_BYTES", total - 1
            ):
                with self.assertRaisesRegex(PackageValidationError, "safety limit"):
                    with open_blendmax(path):
                        yielded = True

            self.assertFalse(yielded)


class _WitnessDirectory:
    """A temp directory that survives its context, for inspecting writes.

    open_blendmax() normally extracts into a TemporaryDirectory that is
    deleted when the context exits -- including on the exception path. These
    tests need to see what had been written at the moment a check refused the
    next write, so they patch the module's tempfile with a witness.
    """

    def __init__(self, root):
        self.root = Path(root)

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        return str(self.root)

    def __exit__(self, *exc_info):
        return False


class ArchivePathCollisionTests(unittest.TestCase):
    """#50: a file member may not also be a directory for another member.

    Both shapes below passed every existing check and died mid-extraction with
    a raw FileExistsError after part of the archive had been written; the fix
    detects them in the preflight that already ran before the first write.
    """

    def test_rejects_file_member_used_as_a_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Collision.blendmax"
            write_package(path, extra={"a": b"file", "a/b": b"nested"})

            with self.assertRaisesRegex(PackageValidationError, "path collision"):
                with open_blendmax(path):
                    pass

    def test_rejects_deep_file_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Deep.blendmax"
            write_package(path, extra={"a/b": b"file", "a/b/c": b"nested"})

            with self.assertRaisesRegex(PackageValidationError, "path collision"):
                with open_blendmax(path):
                    pass

    def test_child_listed_before_the_file_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Reversed.blendmax"
            write_package(path, extra={"b/c": b"nested", "b": b"file"})

            with self.assertRaisesRegex(PackageValidationError, "path collision"):
                with open_blendmax(path):
                    pass

    def test_file_used_as_a_directory_for_real_extraction_is_refused_pre_flight(self):
        # The shape from issue #50's reproduction: geometry "a.fbx" is a real
        # extracted member and texture "a.fbx/x" needs it as a directory.
        # Before the fix this died with a raw FileExistsError after geometry
        # had been written; now it is refused before the temp root exists.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Geometry.blendmax"
            raw = valid_manifest()
            raw["geometry"]["file"] = "a.fbx"
            raw["textures"][0]["package_path"] = "a.fbx/x"
            with zipfile.ZipFile(
                path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("manifest.json", json.dumps(raw))
                archive.writestr("a.fbx", b"geometry")
                archive.writestr("a.fbx/x", b"texture")
            witness = Path(temporary) / "witness"
            stub = mock.Mock()
            stub.TemporaryDirectory = lambda **kwargs: _WitnessDirectory(witness)

            with mock.patch.object(blender_package, "tempfile", stub):
                with self.assertRaisesRegex(PackageValidationError, "path collision"):
                    with open_blendmax(path):
                        pass

            self.assertFalse(witness.exists())

    def test_unreferenced_shadowing_member_is_refused_whole_archive(self):
        # The layout scan is whole-archive, like the duplicate check: this
        # package imported fine before #50 because open_blendmax extracts
        # only declared import data, so the shadowing file member "extra"
        # never landed and nothing collided on disk. It is refused anyway --
        # the archive layout makes a declared texture path unreachable, and
        # normal exporter output cannot produce the shape.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Shadow.blendmax"
            raw = valid_manifest()
            raw["textures"][0]["package_path"] = "extra/x.png"
            write_package(
                path,
                raw,
                extra={"extra": b"never imported", "extra/x.png": b"texture"},
            )
            witness = Path(temporary) / "witness"
            stub = mock.Mock()
            stub.TemporaryDirectory = lambda **kwargs: _WitnessDirectory(witness)

            with mock.patch.object(blender_package, "tempfile", stub):
                with self.assertRaisesRegex(PackageValidationError, "path collision"):
                    with open_blendmax(path):
                        pass

            self.assertFalse(witness.exists())

    def test_accepts_explicit_directory_with_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Dirs.blendmax"
            write_package(path, extra={"dir/": b"", "dir/file.txt": b"x"})

            with open_blendmax(path) as package:
                self.assertEqual(
                    package.texture_paths["textures/wood.png"].read_bytes(), b"image"
                )

    def test_accepts_directory_hierarchy(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Hierarchy.blendmax"
            write_package(path, extra={"a/": b"", "a/b/": b"", "a/b/c": b"y"})

            with open_blendmax(path) as package:
                self.assertEqual(package.geometry_path.read_bytes(), b"fbx")

    def test_existing_duplicate_rejection_keeps_its_precedence(self):
        # Precedence guard, not a new-behaviour test: the duplicate check is
        # interleaved per-member while the collision check runs after the
        # loop, so an archive carrying both defects is rejected exactly as it
        # was before #50 -- existing rejections must not be reordered.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Both.blendmax"
            write_package(
                path,
                extra={"dup.bin": b"1", "DUP.BIN": b"2", "a": b"x", "a/b": b"y"},
            )

            with self.assertRaisesRegex(
                PackageValidationError, "Duplicate archive path"
            ):
                with open_blendmax(path):
                    pass


class ArchiveActualByteBudgetTests(unittest.TestCase):
    """#50: the decompressed bytes actually consumed by one open_blendmax().

    The declared-size preflight is unchanged and still covers every member;
    these tests drive the second, actual-byte check -- streams that return
    more bytes than their headers declared. The budget is cumulative over the
    members actually read by the operation (manifest, geometry, textures).
    """

    TEXTURE = "textures/wood.png"

    @staticmethod
    def _write_package(path, texture_bytes):
        raw = valid_manifest()
        with zipfile.ZipFile(
            path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("manifest.json", json.dumps(raw))
            archive.writestr("geometry.fbx", b"fbx")
            archive.writestr("textures/wood.png", texture_bytes)
        return raw

    @staticmethod
    def _sizes(path):
        with zipfile.ZipFile(path) as archive:
            return {info.filename: info.file_size for info in archive.infolist()}

    def _witness(self, root):
        stub = mock.Mock()
        stub.TemporaryDirectory = lambda **kwargs: _WitnessDirectory(root)
        return mock.patch.object(blender_package, "tempfile", stub)

    def test_manifest_stream_counts_toward_the_budget(self):
        # The budget covers every decompressed stream this operation reads --
        # the manifest included. A lying manifest is refused before the temp
        # root even exists.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Manifest.blendmax"
            self._write_package(path, b"x" * 100)
            sizes = self._sizes(path)
            limit = sum(sizes.values()) + 300
            self.assertGreater(8 * sizes["manifest.json"], limit)
            witness = Path(temporary) / "witness"

            with self._witness(witness):
                with mock.patch.object(
                    blender_package, "MAX_UNCOMPRESSED_BYTES", limit
                ):
                    with _stream_for(
                        "manifest.json", lambda stream: _InflatingStream(stream, 8)
                    ):
                        with self.assertRaisesRegex(
                            PackageValidationError, "safety limit"
                        ):
                            with open_blendmax(path):
                                pass

            self.assertFalse(witness.exists())

    def test_rejects_a_stream_that_exceeds_the_limit_while_declared_under(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Lying.blendmax"
            self._write_package(path, b"x" * 100)
            limit = sum(self._sizes(path).values()) + 300
            self.assertGreater(20 * 100, limit)
            witness = Path(temporary) / "witness"

            with self._witness(witness):
                with mock.patch.object(
                    blender_package, "MAX_UNCOMPRESSED_BYTES", limit
                ):
                    with _stream_for(
                        self.TEXTURE, lambda stream: _InflatingStream(stream, 20)
                    ):
                        with self.assertRaisesRegex(
                            PackageValidationError, "safety limit"
                        ):
                            with open_blendmax(path):
                                pass

            texture = witness / "textures" / "wood.png"
            self.assertTrue(texture.exists())
            self.assertEqual(texture.stat().st_size, 0)

    def test_actual_bytes_are_cumulative_across_extracted_members(self):
        # Premise made explicit: after inflation the texture alone (800
        # bytes) would still fit the limit, so a refusal can only come from
        # counting the bytes already consumed by the manifest and geometry.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Cumulative.blendmax"
            self._write_package(path, b"x" * 100)
            sizes = self._sizes(path)
            limit = sum(sizes.values()) + 300
            self.assertLessEqual(8 * 100, limit)
            self.assertGreater(sizes["manifest.json"] + 3 + 8 * 100, limit)
            witness = Path(temporary) / "witness"

            with self._witness(witness):
                with mock.patch.object(
                    blender_package, "MAX_UNCOMPRESSED_BYTES", limit
                ):
                    with _stream_for(
                        self.TEXTURE, lambda stream: _InflatingStream(stream, 8)
                    ):
                        with self.assertRaisesRegex(
                            PackageValidationError, "safety limit"
                        ):
                            with open_blendmax(path):
                                pass

            self.assertEqual((witness / "geometry.fbx").stat().st_size, 3)
            texture = witness / "textures" / "wood.png"
            self.assertTrue(texture.exists())
            self.assertEqual(texture.stat().st_size, 0)

    def test_accepts_a_lying_stream_that_lands_exactly_on_the_limit(self):
        # Actual bytes exactly on the limit are accepted: the comparison is
        # "> limit", not ">= limit", and every byte still gets written.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "AtLimit.blendmax"
            self._write_package(path, b"x" * 100)
            limit = sum(self._sizes(path).values()) + 2000
            witness = Path(temporary) / "witness"

            with self._witness(witness):
                with mock.patch.object(
                    blender_package, "MAX_UNCOMPRESSED_BYTES", limit
                ):
                    with _stream_for(
                        self.TEXTURE, lambda stream: _PumpingStream(2100, 1000)
                    ):
                        with open_blendmax(path) as package:
                            written = (
                                package.texture_paths[self.TEXTURE].stat().st_size
                            )

            self.assertEqual(written, 2100)

    def test_no_bytes_beyond_the_limit_are_written(self):
        # A stream that keeps producing: the write loop must stop BEFORE the
        # chunk that would cross the limit, leaving a partial member whose
        # size is still within the budget.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Overflow.blendmax"
            self._write_package(path, b"x" * 100)
            limit = sum(self._sizes(path).values()) + 4500
            witness = Path(temporary) / "witness"

            with self._witness(witness):
                with mock.patch.object(
                    blender_package, "MAX_UNCOMPRESSED_BYTES", limit
                ):
                    with _stream_for(
                        self.TEXTURE, lambda stream: _PumpingStream(10000, 1000)
                    ):
                        with self.assertRaisesRegex(
                            PackageValidationError, "safety limit"
                        ):
                            with open_blendmax(path):
                                pass

            written = (witness / "textures" / "wood.png").stat().st_size
            self.assertEqual(written, 4000)
            self.assertLessEqual(3 + written, limit)


if __name__ == "__main__":
    unittest.main()
