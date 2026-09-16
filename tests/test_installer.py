from __future__ import annotations

import runpy
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import blendmax_install
from blendmax_blender import package as blender_package
from blendmax_install import (
    BUNDLE_NAME,
    MAX_ARCHIVE_ENTRIES,
    MAX_UNCOMPRESSED_BYTES,
    InstallError,
    _safe_extract,
    build_bundle,
    install_from_source,
    install_from_zip,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_build_bundle_contains_python_core_and_menu_actions(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE_NAME
            version = build_bundle(SOURCE_ROOT, bundle)

            self.assertEqual(version, "0.1.0-alpha.4.3.0")
            self.assertTrue(
                (bundle / "Contents" / "python" / "blendmax_max" / "exporter.py").is_file()
            )
            self.assertTrue(
                (bundle / "Contents" / "python" / "blendmax_install.py").is_file()
            )
            menu = (
                bundle
                / "Contents"
                / "Post-Start-Up_Scripts"
                / "BlendMaxMenu2025.ms"
            ).read_text(encoding="utf-8")
            self.assertIn("#cuiRegisterMenus", menu)
            self.assertIn("BlendMaxExport`BlendMax", menu)
            self.assertIn("\"Cleanup\"", menu)
            self.assertIn("BlendMaxJoinByMaterial`BlendMax", menu)
            self.assertIn("BlendMaxUpdate`BlendMax", menu)

    def test_manifest_uses_3ds_max_component_categories(self):
        manifest = ET.parse(
            SOURCE_ROOT
            / "appbundle"
            / BUNDLE_NAME
            / "PackageContents.xml"
        ).getroot()
        components = manifest.findall("Components")

        self.assertEqual(
            [component.get("Description") for component in components],
            ["macroscripts parts", "post-start-up scripts parts"],
        )
        self.assertEqual(manifest.get("AppVersion"), "0.1.0.4")
        self.assertEqual(manifest.get("FriendlyVersion"), "0.1.0-alpha.4.3.0")

    def test_launchers_import_actions_when_executed_from_an_isolated_path(self):
        launchers = {
            "launch_export.py": "export_asset",
            "launch_join_by_material.py": "join_mesh_by_material",
            "launch_update.py": "install_update",
            "launch_project_page.py": "open_project_page",
            "launch_about.py": "show_about",
        }
        launcher_source = (
            SOURCE_ROOT
            / "appbundle"
            / BUNDLE_NAME
            / "Contents"
            / "python"
        )
        original_path = list(sys.path)

        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for filename, action in launchers.items():
                    with self.subTest(launcher=filename):
                        isolated = root / Path(filename).stem
                        isolated.mkdir()
                        launcher = isolated / filename
                        shutil.copy2(launcher_source / filename, launcher)
                        marker = isolated / "called.txt"
                        (isolated / "blendmax_actions.py").write_text(
                            "def {0}():\n"
                            "    from pathlib import Path\n"
                            "    Path({1!r}).write_text('called', encoding='utf-8')\n".format(
                                action,
                                str(marker),
                            ),
                            encoding="utf-8",
                        )

                        sys.modules.pop("blendmax_actions", None)
                        sys.path[:] = original_path
                        runpy.run_path(str(launcher), run_name="__blendmax_launcher_test__")

                        self.assertEqual(marker.read_text(encoding="utf-8"), "called")
        finally:
            sys.path[:] = original_path
            sys.modules.pop("blendmax_actions", None)

    def test_launcher_reloads_updated_actions_without_restarting_host(self):
        launcher_source = (
            SOURCE_ROOT
            / "appbundle"
            / BUNDLE_NAME
            / "Contents"
            / "python"
            / "launch_join_by_material.py"
        )
        original_path = list(sys.path)

        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                launcher = root / launcher_source.name
                shutil.copy2(launcher_source, launcher)
                marker = root / "called.txt"
                actions = root / "blendmax_actions.py"
                actions.write_text(
                    "def join_mesh_by_material():\n"
                    "    from pathlib import Path\n"
                    "    Path({0!r}).write_text('old', encoding='utf-8')\n".format(
                        str(marker)
                    ),
                    encoding="utf-8",
                )

                sys.modules.pop("blendmax_actions", None)
                sys.path[:] = original_path
                runpy.run_path(str(launcher), run_name="__blendmax_reload_test_one__")
                self.assertEqual(marker.read_text(encoding="utf-8"), "old")

                actions.write_text(
                    "def join_mesh_by_material():\n"
                    "    from pathlib import Path\n"
                    "    Path({0!r}).write_text('new-version', encoding='utf-8')\n".format(
                        str(marker)
                    ),
                    encoding="utf-8",
                )
                runpy.run_path(str(launcher), run_name="__blendmax_reload_test_two__")

                self.assertEqual(marker.read_text(encoding="utf-8"), "new-version")
        finally:
            sys.path[:] = original_path
            sys.modules.pop("blendmax_actions", None)

    def test_install_replaces_only_the_existing_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugins = Path(temporary) / "ApplicationPlugins"
            target = plugins / BUNDLE_NAME
            target.mkdir(parents=True)
            (target / "stale.txt").write_text("old", encoding="utf-8")
            unrelated = plugins / "AnotherPlugin.bundle"
            unrelated.mkdir()
            (unrelated / "keep.txt").write_text("keep", encoding="utf-8")

            result = install_from_source(SOURCE_ROOT, install_root=plugins)

            self.assertEqual(result["version"], "0.1.0-alpha.4.3.0")
            self.assertFalse((target / "stale.txt").exists())
            self.assertEqual(
                (unrelated / "keep.txt").read_text(encoding="utf-8"),
                "keep",
            )

    def test_install_from_release_zip_with_enclosing_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "BlendMaxUpdate.zip"
            included = (
                "install_blendmax.py",
                "blendmax_install.py",
                "blendmax_max",
                "appbundle",
            )
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name in included:
                    path = SOURCE_ROOT / name
                    files = [path] if path.is_file() else path.rglob("*")
                    for child in files:
                        if not child.is_file() or "__pycache__" in child.parts:
                            continue
                        relative = child.relative_to(SOURCE_ROOT)
                        archive.write(
                            child,
                            (Path("BlendMaxRelease") / relative).as_posix(),
                        )

            plugins = root / "ApplicationPlugins"
            result = install_from_zip(archive_path, install_root=plugins)

            self.assertEqual(result["version"], "0.1.0-alpha.4.3.0")
            self.assertTrue((plugins / BUNDLE_NAME / "PackageContents.xml").is_file())

    def test_rejects_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "nope")

            with self.assertRaises(InstallError):
                install_from_zip(
                    archive_path,
                    install_root=Path(temporary) / "ApplicationPlugins",
                )


class UpdateZipResourceLimitTests(unittest.TestCase):
    """Resource limits for update ZIPs, enforced by _safe_extract().

    Entry-count boundaries are exercised at the REAL constant -- 2048 tiny
    entries is cheap. Byte-budget boundaries patch the constant down instead,
    because testing the real one would mean building a 16 GiB archive; the
    comparison is identical at any value, and the real magnitude is pinned by
    the drift test at the end of this class.
    """

    @staticmethod
    def _build(path, names, size=1):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.writestr(name, b"x" * size)
        return path

    @staticmethod
    def _numbered(count):
        return ["f{0}.txt".format(index) for index in range(count)]

    def _extract(self, archive_path, destination):
        with zipfile.ZipFile(archive_path, "r") as archive:
            _safe_extract(archive, destination)

    # -- entry count ------------------------------------------------------

    def test_accepts_archive_at_entry_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._build(
                Path(temporary) / "ok.zip", self._numbered(MAX_ARCHIVE_ENTRIES)
            )
            destination = Path(temporary) / "out"
            destination.mkdir()

            self._extract(path, destination)

            self.assertEqual(
                len([p for p in destination.rglob("*") if p.is_file()]),
                MAX_ARCHIVE_ENTRIES,
            )

    def test_rejects_archive_above_entry_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._build(
                Path(temporary) / "many.zip", self._numbered(MAX_ARCHIVE_ENTRIES + 1)
            )
            destination = Path(temporary) / "out"
            destination.mkdir()

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            self.assertIn("too many entries", str(caught.exception))

    def test_directory_entries_count_towards_entry_limit(self):
        """Directories consume the entry budget, matching package.py."""
        directories = ["d{0}/".format(index) for index in range(MAX_ARCHIVE_ENTRIES)]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "out"
            destination.mkdir()

            at_limit = self._build(
                Path(temporary) / "dirs.zip", directories, size=0
            )
            self._extract(at_limit, destination)

            over_limit = self._build(
                Path(temporary) / "dirs_over.zip", directories + ["extra/"], size=0
            )
            with self.assertRaises(InstallError) as caught:
                self._extract(over_limit, destination)

            self.assertIn("too many entries", str(caught.exception))

    # -- byte budget ------------------------------------------------------

    def test_accepts_archive_at_byte_limit(self):
        limit = 4096
        with mock.patch.object(blendmax_install, "MAX_UNCOMPRESSED_BYTES", limit):
            with tempfile.TemporaryDirectory() as temporary:
                path = self._build(
                    Path(temporary) / "exact.zip", ["a.bin"], size=limit
                )
                with zipfile.ZipFile(path, "r") as archive:
                    declared = sum(info.file_size for info in archive.infolist())
                self.assertEqual(declared, limit)
                destination = Path(temporary) / "out"
                destination.mkdir()

                self._extract(path, destination)

                self.assertEqual((destination / "a.bin").stat().st_size, limit)

    def test_rejects_archive_above_byte_limit(self):
        limit = 4096
        with mock.patch.object(blendmax_install, "MAX_UNCOMPRESSED_BYTES", limit):
            with tempfile.TemporaryDirectory() as temporary:
                path = self._build(
                    Path(temporary) / "over.zip", ["a.bin"], size=limit + 1
                )
                destination = Path(temporary) / "out"
                destination.mkdir()

                with self.assertRaises(InstallError) as caught:
                    self._extract(path, destination)

                self.assertIn("safety limit", str(caught.exception))

    # -- nothing written when preflight fails ------------------------------

    def test_destination_untouched_when_entry_limit_exceeded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._build(
                Path(temporary) / "many.zip", self._numbered(MAX_ARCHIVE_ENTRIES + 1)
            )
            destination = Path(temporary) / "out"
            destination.mkdir()

            with self.assertRaises(InstallError):
                self._extract(path, destination)

            self.assertEqual(list(destination.rglob("*")), [])

    def test_destination_untouched_when_byte_budget_exceeded(self):
        with mock.patch.object(blendmax_install, "MAX_UNCOMPRESSED_BYTES", 64):
            with tempfile.TemporaryDirectory() as temporary:
                path = self._build(
                    Path(temporary) / "over.zip",
                    ["small.txt", "big.bin"],
                    size=65,
                )
                destination = Path(temporary) / "out"
                destination.mkdir()

                with self.assertRaises(InstallError):
                    self._extract(path, destination)

                self.assertEqual(list(destination.rglob("*")), [])

    # -- existing protections preserved ------------------------------------

    def test_rejects_symlink_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "link.zip"
            with zipfile.ZipFile(path, "w") as archive:
                info = zipfile.ZipInfo("link")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "target.txt")
            destination = Path(temporary) / "out"
            destination.mkdir()

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            self.assertIn("symbolic link", str(caught.exception))

    def test_rejects_path_traversal_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "escape.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape.txt", "nope")
            destination = Path(temporary) / "out" / "inner"
            destination.mkdir(parents=True)

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            self.assertIn("unsafe path", str(caught.exception))

    # -- end to end, and the drift guard -----------------------------------

    def test_install_from_zip_rejects_archive_above_byte_limit(self):
        with mock.patch.object(blendmax_install, "MAX_UNCOMPRESSED_BYTES", 64):
            with tempfile.TemporaryDirectory() as temporary:
                path = self._build(
                    Path(temporary) / "over.zip", ["big.bin"], size=65
                )
                plugins = Path(temporary) / "ApplicationPlugins"

                with self.assertRaises(InstallError) as caught:
                    install_from_zip(path, install_root=plugins)

                self.assertIn("safety limit", str(caught.exception))
                self.assertFalse((plugins / BUNDLE_NAME).exists())

    def test_limits_match_the_canonical_package_limits(self):
        """These constants are duplicated for deployment reasons; they must not
        drift from blendmax_blender.package."""
        self.assertEqual(MAX_ARCHIVE_ENTRIES, blender_package.MAX_ARCHIVE_ENTRIES)
        self.assertEqual(
            MAX_UNCOMPRESSED_BYTES, blender_package.MAX_UNCOMPRESSED_BYTES
        )


class UpdateZipSecurityRegressionTests(unittest.TestCase):
    """Security regressions on the update-ZIP path.

    Symlink, absolute-path and leading-traversal rejection for this path live in
    InstallerTests and UpdateZipResourceLimitTests. What is added here is a
    nested traversal form, and the guarantee that a refusal leaves a destination
    which already has contents exactly as it found it.
    """

    def _extract(self, archive_path, destination):
        with zipfile.ZipFile(archive_path, "r") as archive:
            _safe_extract(archive, destination)

    @staticmethod
    def _populated_destination(temporary):
        destination = Path(temporary) / "out"
        destination.mkdir()
        existing = destination / "keep.txt"
        existing.write_text("preexisting", encoding="utf-8")
        return destination, existing

    def test_rejects_nested_traversal_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("a/../../escape.txt", "nope")
            destination = Path(temporary) / "out" / "inner"
            destination.mkdir(parents=True)

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            self.assertIn("unsafe path", str(caught.exception))
            self.assertEqual(list(destination.rglob("*")), [])

    def test_existing_destination_unchanged_when_byte_budget_rejected(self):
        with mock.patch.object(blendmax_install, "MAX_UNCOMPRESSED_BYTES", 64):
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "over.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("big.bin", b"x" * 65)
                destination, existing = self._populated_destination(temporary)

                with self.assertRaises(InstallError):
                    self._extract(path, destination)

                self.assertEqual(
                    sorted(item.name for item in destination.iterdir()), ["keep.txt"]
                )
                self.assertEqual(existing.read_text(encoding="utf-8"), "preexisting")

    def test_existing_destination_unchanged_when_entry_limit_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "many.zip"
            with zipfile.ZipFile(path, "w") as archive:
                for index in range(MAX_ARCHIVE_ENTRIES + 1):
                    archive.writestr("f{0}.txt".format(index), b"x")
            destination, existing = self._populated_destination(temporary)

            with self.assertRaises(InstallError):
                self._extract(path, destination)

            self.assertEqual(
                sorted(item.name for item in destination.iterdir()), ["keep.txt"]
            )
            self.assertEqual(existing.read_text(encoding="utf-8"), "preexisting")


if __name__ == "__main__":
    unittest.main()
