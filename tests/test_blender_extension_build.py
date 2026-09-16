from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import blendmax_blender
from tools import build_blender_extension as builder
from tools.build_blender_extension import build


class BlenderExtensionBuildTests(unittest.TestCase):
    def test_build_has_manifest_and_extension_at_archive_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build(Path(temporary) / "blendmax_importer.zip")
            with zipfile.ZipFile(output, "r") as archive:
                names = archive.namelist()
                metadata = tomllib.loads(
                    archive.read("blender_manifest.toml").decode("utf-8")
                )

            self.assertIn("__init__.py", names)
            self.assertIn("addon.py", names)
            self.assertNotIn("blendmax_blender/__init__.py", names)
            self.assertEqual(metadata["id"], "blendmax_importer")
            self.assertEqual(metadata["version"], "0.1.9")
            self.assertEqual(metadata["blender_version_min"], "4.2.0")

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = build(root / "first.zip")
            second = build(root / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())


class BlenderVersionMetadataTests(unittest.TestCase):
    """The Blender importer's version is declared in three places.

    Only ``blender_manifest.toml`` is consumed: Blender 4.2+ reads it for an
    installed extension, and ``tools/build_blender_extension.py`` names the
    built artifact from it. ``__init__.py``'s ``__version__`` and the legacy
    ``bl_info`` dict are informational, and nothing in the repository reads
    them -- which is why ``bl_info`` sat at ``0.1.8`` through the whole 0.1.9
    release without anything noticing. Every test here fails if the three
    declarations disagree, so that drift cannot recur silently.

    The 3ds Max component is deliberately NOT compared against these values:
    it versions as ``0.1.0-alpha.4.3.0``, a different scheme for a different
    artifact.
    """

    @staticmethod
    def _manifest_on_disk():
        return tomllib.loads(
            (
                Path(blendmax_blender.__file__).parent / "blender_manifest.toml"
            ).read_text(encoding="utf-8")
        )

    @staticmethod
    def _expected_bl_info_version():
        return tuple(int(part) for part in blendmax_blender.__version__.split("."))

    # -- the three declarations agree -------------------------------------

    def test_dunder_version_matches_the_extension_manifest(self):
        self.assertEqual(
            blendmax_blender.__version__, self._manifest_on_disk()["version"]
        )

    def test_bl_info_version_matches_dunder_version(self):
        self.assertEqual(
            blendmax_blender.bl_info["version"], self._expected_bl_info_version()
        )

    def test_manifest_version_is_major_minor_patch(self):
        """Blender requires a three-part numeric version for an extension."""
        version = self._manifest_on_disk()["version"]
        parts = version.split(".")
        self.assertEqual(len(parts), 3, version)
        for part in parts:
            self.assertTrue(part.isdigit(), version)

    # -- the generated artifact and build agree with it -------------------

    def test_generated_artifact_reports_the_manifest_version(self):
        """Read the version out of the real artifact rather than a constant."""
        expected = self._manifest_on_disk()["version"]
        with tempfile.TemporaryDirectory() as temporary:
            output = build(Path(temporary) / "artifact.zip")
            with zipfile.ZipFile(output, "r") as archive:
                built = tomllib.loads(
                    archive.read("blender_manifest.toml").decode("utf-8")
                )
        self.assertEqual(built["version"], expected)

    def _default_artifact_name(self):
        # main() prints the build result; keep that out of the test output.
        with mock.patch.object(builder, "build") as fake_build:
            with mock.patch.object(sys, "argv", ["build_blender_extension.py"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    builder.main()
        return fake_build.call_args[0][0].name

    def test_default_artifact_name_embeds_the_manifest_version(self):
        expected = self._manifest_on_disk()["version"]
        self.assertEqual(
            self._default_artifact_name(),
            "blendmax_importer-{0}.zip".format(expected),
        )

    def test_artifact_name_follows_the_manifest_rather_than_a_constant(self):
        """Proves the build reads the version instead of hard-coding it."""
        with mock.patch.object(builder, "manifest", lambda: {"version": "9.9.9"}):
            self.assertEqual(
                self._default_artifact_name(), "blendmax_importer-9.9.9.zip"
            )

    # -- the manifest stays valid for Blender ------------------------------

    def test_extension_manifest_keeps_blenders_required_keys(self):
        metadata = self._manifest_on_disk()
        for key in (
            "schema_version",
            "id",
            "version",
            "name",
            "tagline",
            "maintainer",
            "type",
            "blender_version_min",
            "license",
        ):
            with self.subTest(key=key):
                self.assertIn(key, metadata)
        self.assertEqual(metadata["id"], "blendmax_importer")
        self.assertEqual(metadata["type"], "add-on")


if __name__ == "__main__":
    unittest.main()
