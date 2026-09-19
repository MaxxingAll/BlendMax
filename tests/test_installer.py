from __future__ import annotations

import os
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import blendmax_archive_policy as archive_policy
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
                "blendmax_archive_policy.py",
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

    def test_limits_come_from_the_shared_policy_module(self):
        """These constants are no longer duplicated, so they cannot drift.

        They used to be two literals in two artifacts held together by this
        test. Both consumers now bind them from blendmax_archive_policy, so the
        equality is a consequence of the sharing rather than a thing to
        remember to maintain.
        """
        self.assertIs(MAX_ARCHIVE_ENTRIES, archive_policy.MAX_ARCHIVE_ENTRIES)
        self.assertIs(MAX_UNCOMPRESSED_BYTES, archive_policy.MAX_UNCOMPRESSED_BYTES)
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


class UpdateZipWindowsHazardTests(unittest.TestCase):
    """The gap #39 reported: update ZIPs now apply the shared filename policy.

    Before this change the update path rejected absolute paths, symlinks and
    traversal, but accepted "CON", "dir/NUL.txt", "name." and "a/b:c". Every
    rejection below fails against the pre-change _safe_extract.
    """

    def _extract(self, archive_path, destination):
        with zipfile.ZipFile(archive_path, "r") as archive:
            _safe_extract(archive, destination)

    @staticmethod
    def _archive(temporary, names):
        path = Path(temporary) / "probe.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name in names:
                archive.writestr(name, b"x")
        return path

    @staticmethod
    def _destination(temporary):
        destination = Path(temporary) / "out"
        destination.mkdir()
        return destination

    def _assert_rejected(self, name, *expected_fragments):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._archive(temporary, [name])
            destination = self._destination(temporary)

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            message = str(caught.exception)
            for fragment in expected_fragments:
                self.assertIn(fragment, message)
            # A refusal is a pre-flight check: nothing may reach the disk.
            self.assertEqual(sorted(item.name for item in destination.iterdir()), [])
            return message

    def test_rejects_reserved_device_name(self):
        self._assert_rejected("CON", "unsafe path", "reserved Windows device name")

    def test_rejects_reserved_device_name_case_insensitively(self):
        self._assert_rejected("con", "reserved Windows device name")

    def test_rejects_reserved_name_with_an_extension(self):
        self._assert_rejected("NUL.txt", "reserved Windows device name")

    def test_rejects_reserved_name_in_an_intermediate_directory(self):
        message = self._assert_rejected(
            "dir/NUL.txt", "unsafe path", "reserved Windows device name"
        )
        self.assertIn("'NUL.txt'", message)

    def test_rejects_serial_device_names(self):
        self._assert_rejected("COM1", "reserved Windows device name")

    def test_rejects_superscript_device_name(self):
        self._assert_rejected("COM\u00b9", "reserved Windows device name")

    def test_rejects_trailing_dot(self):
        self._assert_rejected("name.", "trailing dot or space")

    def test_rejects_trailing_space(self):
        self._assert_rejected("name ", "trailing dot or space")

    def test_rejects_colon_in_a_component(self):
        self._assert_rejected("a/b:c", "colon is not allowed in a path component")

    def test_rejects_drive_relative_colon(self):
        self._assert_rejected("C:file", "colon is not allowed in a path component")

    def test_rejects_case_insensitive_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._archive(temporary, ["Readme.md", "README.MD"])
            destination = self._destination(temporary)

            with self.assertRaises(InstallError) as caught:
                self._extract(path, destination)

            self.assertIn("duplicate path", str(caught.exception))
            self.assertEqual(sorted(item.name for item in destination.iterdir()), [])

    def test_existing_destination_untouched_when_a_hazard_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._archive(temporary, ["ok.txt", "CON"])
            destination, existing = self._populated(temporary)

            with self.assertRaises(InstallError):
                self._extract(path, destination)

            self.assertEqual(sorted(item.name for item in destination.iterdir()),
                             ["keep.txt"])
            self.assertEqual(existing.read_text(encoding="utf-8"), "preexisting")

    @staticmethod
    def _populated(temporary):
        destination = Path(temporary) / "out"
        destination.mkdir()
        existing = destination / "keep.txt"
        existing.write_text("preexisting", encoding="utf-8")
        return destination, existing

    # -- the policy must not over-block -----------------------------------

    def test_accepts_ordinary_paths(self):
        names = ["textures/wood.png", "a/b/c.txt", "readme.md", "dir\\win.txt"]
        with tempfile.TemporaryDirectory() as temporary:
            path = self._archive(temporary, names)
            destination = self._destination(temporary)

            self._extract(path, destination)

            self.assertTrue((destination / "textures" / "wood.png").is_file())
            self.assertTrue((destination / "a" / "b" / "c.txt").is_file())
            # Backslashes from a Windows-written archive are separators.
            self.assertTrue((destination / "dir" / "win.txt").is_file())

    def test_accepts_the_documented_boundaries(self):
        names = ["COM0", "LPT0", "COM10", "LPT10", "CLOCK$", "COM\u2074"]
        with tempfile.TemporaryDirectory() as temporary:
            path = self._archive(temporary, names)
            destination = self._destination(temporary)

            self._extract(path, destination)

            for name in names:
                self.assertTrue((destination / name).is_file(), name)


class ArchivePolicyDeploymentTests(unittest.TestCase):
    """Both SHIPPED artifacts must carry the shared policy and be able to use it.

    A source-tree import proves nothing about the artifacts: the Blender
    extension ships only blendmax_blender/ (flattened to the archive root) and
    the Max bundle ships only Contents/python. These tests build both and check
    them as artifacts, which is the only way to catch the shared module being
    present in the repository but absent from a release.
    """

    def test_bundle_contains_the_shared_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE_NAME
            build_bundle(SOURCE_ROOT, bundle)

            self.assertTrue(
                (bundle / "Contents" / "python" / "blendmax_archive_policy.py").is_file()
            )

    def test_bundle_does_not_contain_blender_code(self):
        """The Max bundle must not depend on the Blender artifact."""
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE_NAME
            build_bundle(SOURCE_ROOT, bundle)

            self.assertFalse((bundle / "Contents" / "python" / "blendmax_blender").exists())

    def test_shipped_policy_is_byte_identical_to_the_canonical_file(self):
        """Neither artifact may carry a forked copy of the rules."""
        canonical = (SOURCE_ROOT / "blendmax_archive_policy.py").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE_NAME
            build_bundle(SOURCE_ROOT, bundle)

            shipped = (
                bundle / "Contents" / "python" / "blendmax_archive_policy.py"
            ).read_bytes()
            self.assertEqual(shipped, canonical)

    def test_deployed_installer_imports_and_enforces_the_policy(self):
        """Run the installed bundle the way 3ds Max does: Contents/python only.

        The subprocess deliberately has no repository on sys.path, so this
        fails if the bundle is missing the shared module rather than silently
        falling back to the developer's working tree.
        """
        probe = "\n".join([
            "import sys, tempfile, zipfile",
            "from pathlib import Path",
            "import blendmax_install as installer",
            "print('POLICY', Path(installer.archive_policy.__file__).name)",
            "print('LIMITS', installer.MAX_ARCHIVE_ENTRIES)",
            "verdicts = {}",
            "with tempfile.TemporaryDirectory() as tmp:",
            "    dest = Path(tmp) / 'out'",
            "    dest.mkdir()",
            "    for name in ('CON', 'textures/wood.png'):",
            "        p = Path(tmp) / 'a.zip'",
            "        with zipfile.ZipFile(p, 'w') as z:",
            "            z.writestr(name, b'x')",
            "        with zipfile.ZipFile(p) as z:",
            "            try:",
            "                installer._safe_extract(z, dest)",
            "                verdicts[name] = 'ACCEPTED'",
            "            except installer.InstallError:",
            "                verdicts[name] = 'REJECTED'",
            "print('VERDICT_CON', verdicts['CON'])",
            "print('VERDICT_OK', verdicts['textures/wood.png'])",
        ])
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE_NAME
            build_bundle(SOURCE_ROOT, bundle)
            python_root = bundle / "Contents" / "python"

            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=str(python_root),
                env=environment,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr[-1200:])
            self.assertIn("POLICY blendmax_archive_policy.py", completed.stdout)
            self.assertIn("LIMITS 2048", completed.stdout)
            # Enforced from inside the bundle, with the repository off sys.path.
            self.assertIn("VERDICT_CON REJECTED", completed.stdout)
            self.assertIn("VERDICT_OK ACCEPTED", completed.stdout)


if __name__ == "__main__":
    unittest.main()
