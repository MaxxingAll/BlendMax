from __future__ import annotations

import unittest

from blendmax_max.errors import CleanupError
from blendmax_max.max_cleanup_adapter import MaxCleanupAdapter


class SlotMaterial:
    """A Multi/Sub material exposing the two host lists."""

    def __init__(self, material_ids, materials, name="MultiSub"):
        self.materialIDList = list(material_ids)
        self.materialList = list(materials)
        self.name = name


class LeafMaterial:
    def __init__(self, name):
        self.name = name


class _PolyOp:
    def __init__(self, face_count):
        self._face_count = face_count

    def getNumFaces(self, node):
        return self._face_count


class PieceRuntime:
    """Minimum runtime surface for _pieces_from_node."""

    undefined = object()

    def __init__(self, face_material_sets, face_count=6):
        # (material_id, face_indices) pairs as the host would report them.
        self._face_material_sets = list(face_material_sets)
        self.deleted = []
        self.split_calls = []
        self.polyop = _PolyOp(face_count)

    def delete(self, node):
        self.deleted.append(node)


class PiecesFromNodeSlotTests(unittest.TestCase):
    """_pieces_from_node against valid and inconsistent slot data."""

    def _adapter(self, face_material_sets):
        adapter = MaxCleanupAdapter.__new__(MaxCleanupAdapter)
        runtime = PieceRuntime(face_material_sets)
        adapter.rt = runtime
        adapter._nodes_by_id = {}

        adapter._copy_as_editable_poly = lambda source, created: source
        adapter._face_sets_by_material_id = (
            lambda staging: list(runtime._face_material_sets)
        )
        adapter._replacement_material = lambda material, replacements: material
        adapter._normalize_face_material_ids = lambda node: None
        adapter._is_undefined = lambda value: value is None
        adapter._bucket_identity = lambda material, **kwargs: (
            "key-" + str(getattr(material, "name", "none")),
            material,
            "label",
        )
        # Detaching is host-side splitting machinery, unrelated to slot
        # resolution; return a distinct stand-in node per call.
        counter = {"n": 0}

        class Piece:
            material = None

            def __init__(self, index):
                self.index = index
                self.name = "piece-{0}".format(index)

        def fake_detach(staging, face_selection, created_nodes):
            counter["n"] += 1
            return Piece(counter["n"])

        adapter._detach_piece = fake_detach
        return adapter, runtime

    def _source(self, material):
        class Source:
            name = "Source"

        source = Source()
        source.material = material
        return source

    def test_equal_length_slot_lists_resolve_face_ids(self):
        red = LeafMaterial("Red")
        blue = LeafMaterial("Blue")
        material = SlotMaterial([1, 2], [red, blue])

        adapter, _ = self._adapter([(1, [0, 1]), (2, [2, 3])])
        pieces = adapter._pieces_from_node(
            self._source(material), created_nodes=[], warnings=[]
        )

        self.assertEqual(len(pieces), 2)
        self.assertEqual({piece[1].name for piece in pieces}, {"Red", "Blue"})

    def test_unknown_face_material_id_uses_the_warning_path(self):
        """A valid lookup with an unmatched face ID still warns, not raises."""
        red = LeafMaterial("Red")
        material = SlotMaterial([1], [red])

        adapter, _ = self._adapter([(1, [0, 1]), (9, [2, 3])])
        warnings = []
        pieces = adapter._pieces_from_node(
            self._source(material), created_nodes=[], warnings=warnings
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("unresolved Multi/Sub material ID(s)", warnings[0])
        self.assertIn("9", warnings[0])
        # Both the resolved and the unresolved face set produce a piece.
        self.assertEqual(len(pieces), 2)

    def test_more_ids_than_materials_raises_instead_of_truncating(self):
        red = LeafMaterial("Red")
        material = SlotMaterial([1, 2, 3], [red])

        adapter, _ = self._adapter([(1, [0, 1])])
        with self.assertRaisesRegex(CleanupError, "Multi/Sub material slot mismatch"):
            adapter._pieces_from_node(
                self._source(material), created_nodes=[], warnings=[]
            )

    def test_more_materials_than_ids_raises_instead_of_truncating(self):
        material = SlotMaterial([1], [LeafMaterial("Red"), LeafMaterial("Blue")])

        adapter, _ = self._adapter([(1, [0, 1])])
        with self.assertRaisesRegex(CleanupError, "Multi/Sub material slot mismatch"):
            adapter._pieces_from_node(
                self._source(material), created_nodes=[], warnings=[]
            )

    def test_uneven_slot_lists_do_not_silently_import(self):
        """A mismatched pair must not produce a truncated-but-valid import."""
        material = SlotMaterial([1, 2], [LeafMaterial("Red")])

        adapter, _ = self._adapter([(1, [0, 1]), (2, [2, 3])])
        with self.assertRaises(CleanupError):
            adapter._pieces_from_node(
                self._source(material), created_nodes=[], warnings=[]
            )

    def test_empty_ids_with_one_material_raises_through_the_adapter(self):
        """Regression: the empty-list early return used to skip the validator.

        ``_material_slots`` returned None whenever EITHER list was empty, so
        ``[] / [m]`` and ``[1] / []`` were silently routed to the plain-material
        fallback instead of being reported as an inconsistent pair.
        """
        material = SlotMaterial([], [LeafMaterial("Red")])

        adapter, _ = self._adapter([(1, [0, 1])])
        with self.assertRaisesRegex(CleanupError, "Multi/Sub material slot mismatch"):
            adapter._pieces_from_node(
                self._source(material), created_nodes=[], warnings=[]
            )

    def test_one_id_with_empty_materials_raises_through_the_adapter(self):
        material = SlotMaterial([1], [])

        adapter, _ = self._adapter([(1, [0, 1])])
        with self.assertRaisesRegex(CleanupError, "Multi/Sub material slot mismatch"):
            adapter._pieces_from_node(
                self._source(material), created_nodes=[], warnings=[]
            )

    def test_both_lists_empty_is_not_a_mismatch(self):
        """Two empty lists mean 'no Multi/Sub slots', keeping the fallback."""
        material = SlotMaterial([], [])

        adapter, _ = self._adapter([(1, [0, 1])])
        pieces = adapter._pieces_from_node(
            self._source(material), created_nodes=[], warnings=[]
        )

        # Plain-material fallback: the whole node is one piece, no warning.
        self.assertEqual(len(pieces), 1)

    def test_undefined_material_short_circuits_without_validating(self):
        adapter, _ = self._adapter([(1, [0, 1])])

        class Source:
            name = "Source"

        source = Source()
        source.material = adapter.rt.undefined
        pieces = adapter._pieces_from_node(source, created_nodes=[], warnings=[])

        self.assertEqual(len(pieces), 1)


if __name__ == "__main__":
    unittest.main()
