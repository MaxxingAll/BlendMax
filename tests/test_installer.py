from __future__ import annotations

import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from blendmax_install import (
    BUNDLE_NAME,
    InstallError,
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

            self.assertEqual(version, "0.1.0-alpha.3.1")
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
        self.assertEqual(manifest.get("FriendlyVersion"), "0.1.0-alpha.3.1")

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

            self.assertEqual(result["version"], "0.1.0-alpha.3.1")
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

            self.assertEqual(result["version"], "0.1.0-alpha.3.1")
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


if __name__ == "__main__":
    unittest.main()
