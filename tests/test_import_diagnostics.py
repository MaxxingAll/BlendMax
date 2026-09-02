from __future__ import annotations

import unittest
from types import SimpleNamespace

from blendmax_blender.diagnostics import categorize_import_messages
from blendmax_blender.models import GraphNode, ImportSummary


GLOSSINESS_MARKER = (
    " has separate reflection and refraction glossiness values; Blender's "
    "Principled shader uses a single roughness for both, so the refraction "
    "roughness is approximated."
)


def package(*nodes):
    return SimpleNamespace(manifest=SimpleNamespace(graph=nodes))


def summary(warnings=(), notes=()):
    return ImportSummary("asset", 1, 1, 0, tuple(warnings), tuple(notes))


class ImportDiagnosticsTests(unittest.TestCase):
    def test_known_unsupported_fields_become_one_sorted_note(self):
        node = GraphNode(
            "m1", "material", "VRayMtl", "Mat",
            {"Translucency_On": True, "BRDF_Type": 1, "vray_future_parameter": 2},
        )
        result = categorize_import_messages(summary(), package(node))
        self.assertEqual(result.warnings, ())
        self.assertEqual(
            result.notes,
            ("(brdf_type/translucency_on) is not supported yet, wait for future BlendMax updates",),
        )

    def test_unexpected_and_texture_warnings_remain_warnings(self):
        warnings = (
            "VRayMtl parameter vray_future_parameter has no Blender mapping yet.",
            "Packaged image for texture graph node tex_2140 is unavailable.",
        )
        result = categorize_import_messages(summary(warnings), package())
        self.assertEqual(result.warnings, warnings)
        self.assertEqual(result.notes, ())

    def test_glossiness_materials_become_one_unique_grouped_note(self):
        warnings = (
            "Mat B" + GLOSSINESS_MARKER,
            "Mat A" + GLOSSINESS_MARKER,
            "Mat B" + GLOSSINESS_MARKER,
            "ordinary warning",
        )
        result = categorize_import_messages(summary(warnings), package())
        self.assertEqual(result.warnings, ("ordinary warning",))
        self.assertEqual(result.notes, ("(Mat B/Mat A)" + GLOSSINESS_MARKER,))

    def test_mapped_only_materials_emit_nothing(self):
        node = GraphNode("m1", "material", "VRayMtl", "Mat", {"diffuse": [1, 1, 1]})
        result = categorize_import_messages(summary(), package(node))
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.notes, ())


if __name__ == "__main__":
    unittest.main()
