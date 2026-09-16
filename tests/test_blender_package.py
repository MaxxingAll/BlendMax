from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from blendmax_blender.errors import PackageValidationError
from blendmax_blender.package import _safe_name, open_blendmax
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


if __name__ == "__main__":
    unittest.main()
