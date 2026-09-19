from __future__ import annotations

import contextlib
import importlib
import io
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import blendmax_archive_policy as archive_policy
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
    """The Blender importer's version is declared in three production places.

    Only ``blender_manifest.toml`` is consumed: Blender 4.2+ reads it for an
    installed extension, and ``tools/build_blender_extension.py`` names the
    built artifact from it. ``__init__.py``'s ``__version__`` and the legacy
    ``bl_info`` dict are informational, and nothing in the repository reads
    them -- which is why ``bl_info`` sat at ``0.1.8`` through the whole 0.1.9
    release without anything noticing. Every test here fails if those three
    disagree, so that drift cannot recur silently.

    A fourth value must also move on release: the literal ``"0.1.9"`` asserted
    by :class:`BlenderExtensionBuildTests`. It is an independent expectation
    rather than a declaration, so it is deliberately left in step by hand.

    The 3ds Max component is deliberately NOT compared against these values:
    it versions as ``0.1.0-alpha.4.3.0``, a different scheme for a different
    artifact.
    """

    @staticmethod
    def _manifest_on_disk():
        # Read through the builder's own root, so this compares the file the
        # build actually consumes rather than wherever the package happens to
        # be imported from.
        return tomllib.loads(
            (builder.SOURCE_ROOT / "blender_manifest.toml").read_text(
                encoding="utf-8"
            )
        )

    def _expected_bl_info_version(self):
        """Parse __version__, failing cleanly if it is not major.minor.patch."""
        version = blendmax_blender.__version__
        parts = version.split(".")
        self.assertEqual(len(parts), 3, version)
        for part in parts:
            self.assertTrue(part.isdigit(), version)
        return tuple(int(part) for part in parts)

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

    def test_dunder_version_is_major_minor_patch(self):
        """__version__ is parsed into bl_info's tuple, so it must be numeric.

        Without this, a malformed __version__ would surface as a ValueError
        raised inside the comparison test rather than as a clean failure.
        """
        version = blendmax_blender.__version__
        parts = version.split(".")
        self.assertEqual(len(parts), 3, version)
        for part in parts:
            with self.subTest(part=part):
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
        with mock.patch.object(builder, "build") as fake_build, \
                mock.patch.object(
                    sys, "argv", ["build_blender_extension.py"]
                ), \
                contextlib.redirect_stdout(io.StringIO()):
            builder.main()
        call = fake_build.call_args
        target = call.kwargs.get("output")
        if target is None and call.args:
            target = call.args[0]
        return target.name

    def test_default_artifact_name_embeds_the_manifest_version(self):
        expected = self._manifest_on_disk()["version"]
        self.assertEqual(
            self._default_artifact_name(),
            "blendmax_importer-{0}.zip".format(expected),
        )

    def test_artifact_name_follows_the_manifest_rather_than_a_constant(self):
        """Proves the build reads the version instead of hard-coding it."""
        with mock.patch.object(
            builder, "manifest", return_value={"version": "9.9.9"}
        ):
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


class SharedPolicyPackagingTests(unittest.TestCase):
    """The built extension must carry the shared archive policy and be able to use it.

    The extension ships ``blendmax_blender/`` flattened to the archive root, and
    that root becomes the import package. The shared policy therefore has to be
    written to that root by the build, where package.py reaches it as a sibling
    module. Importing it from the repository working tree would prove nothing.
    """

    @staticmethod
    def _build_and_extract(temporary):
        output = build(Path(temporary) / "blendmax_importer.zip")
        root = Path(temporary) / "extroot"
        with zipfile.ZipFile(output, "r") as archive:
            names = archive.namelist()
            archive.extractall(root / "extension")
        return names, root

    def test_shared_policy_is_in_the_built_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            names, _ = self._build_and_extract(temporary)

            self.assertIn("blendmax_archive_policy.py", names)

    def test_shared_policy_sits_beside_the_package_modules(self):
        """Flattened to the root, so the relative import in package.py resolves."""
        with tempfile.TemporaryDirectory() as temporary:
            names, _ = self._build_and_extract(temporary)

            self.assertIn("package.py", names)
            self.assertNotIn("blendmax_blender/blendmax_archive_policy.py", names)
            self.assertFalse([name for name in names if name.startswith("blendmax_blender/")])

    def test_extension_does_not_contain_max_deployment_code(self):
        """The Blender artifact must not depend on the 3ds Max bundle."""
        with tempfile.TemporaryDirectory() as temporary:
            names, _ = self._build_and_extract(temporary)

            self.assertFalse([name for name in names if name.startswith("blendmax_max")])
            self.assertNotIn("blendmax_install.py", names)

    def test_shipped_policy_is_byte_identical_to_the_canonical_file(self):
        """The artifact must not carry a forked copy of the rules."""
        with tempfile.TemporaryDirectory() as temporary:
            output = build(Path(temporary) / "blendmax_importer.zip")
            with zipfile.ZipFile(output, "r") as archive:
                shipped = archive.read("blendmax_archive_policy.py")

            canonical = (builder.PROJECT_ROOT / "blendmax_archive_policy.py").read_bytes()
            self.assertEqual(shipped, canonical)

    def test_built_extension_imports_and_uses_the_policy(self):
        """Import the extracted extension as a package, the way Blender loads it."""
        with tempfile.TemporaryDirectory() as temporary:
            _, root = self._build_and_extract(temporary)
            sys.path.insert(0, str(root))
            try:
                package = importlib.import_module("extension.package")
                errors = importlib.import_module("extension.errors")

                self.assertTrue(
                    package.archive_policy.__file__.endswith("blendmax_archive_policy.py")
                )
                # Importing it is not enough: it has to be the module actually
                # deciding, so exercise a rejection through the built package.
                with self.assertRaises(errors.PackageValidationError):
                    package._safe_name("CON")
                with self.assertRaises(errors.PackageValidationError):
                    package._safe_name("dir/NUL.txt")
                self.assertEqual(
                    package._safe_name("textures/wood.png"), "textures/wood.png"
                )
            finally:
                sys.path.remove(str(root))
                for name in [n for n in sys.modules if n == "extension"
                             or n.startswith("extension.")]:
                    del sys.modules[name]

    def test_extension_policy_agrees_with_the_canonical_rules(self):
        """A sample of the rules, checked against the imported shared module."""
        self.assertEqual(archive_policy.windows_hazard("CON"),
                         "reserved Windows device name")
        self.assertEqual(archive_policy.windows_hazard("COM10"), "")


if __name__ == "__main__":
    unittest.main()
