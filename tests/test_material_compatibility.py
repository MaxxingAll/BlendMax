from __future__ import annotations

import unittest

from blendmax_blender.material_compatibility import (
    KNOWN_UNMAPPED_PARAMETERS,
    known_unmapped_parameters,
)


class MaterialCompatibilityTests(unittest.TestCase):
    def test_registry_is_case_insensitive_by_material_class(self):
        self.assertEqual(
            known_unmapped_parameters("VRAYMTL"),
            KNOWN_UNMAPPED_PARAMETERS["vraymtl"],
        )

    def test_vray_known_gap_is_registered(self):
        known = known_unmapped_parameters("VrayMtl")
        self.assertIn("brdf_type", known)
        self.assertIn("refraction_maxdepth", known)

    def test_physical_material_registry_is_ready_without_claiming_gaps(self):
        self.assertEqual(known_unmapped_parameters("PhysicalMaterial"), frozenset())

    def test_unknown_material_class_has_no_registered_gaps(self):
        self.assertEqual(known_unmapped_parameters("FutureMaterial"), frozenset())


if __name__ == "__main__":
    unittest.main()
