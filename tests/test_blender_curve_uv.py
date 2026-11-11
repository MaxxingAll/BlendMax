"""Blender-side contract tests for Curve UV > Project From View.

``blender_curve_uv`` runs against a small fake ``bpy``. The projection math is
covered in ``test_curve_uv.py``; these tests cover the glue: one modifier on
the Curve itself, one shared node group, the stored view, idempotent re-runs,
viewport lookup and selection handling. Whether Blender really evaluates the
node group into a UV map is a host test (``BLENDER_IMPORTER_TEST_MATRIX.md``).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

try:
    from fakes import FakeMatrix, FakeVector, load_blender_module
except ImportError:  # dotted-module invocation from the repository root
    from tests.fakes import FakeMatrix, FakeVector, load_blender_module


# One triangle in local space, on screen with the identity view.
TRIANGLE = ((0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0))
GROUP_KEY = "blendmax_curve_uv_group"


class FakeIdProperties:
    """Custom-property surface shared by the fake datablocks."""

    def get(self, key, default=None):
        return self.__dict__.setdefault("_properties", {}).get(key, default)

    def __setitem__(self, key, value):
        self.__dict__.setdefault("_properties", {})[key] = value

    def __getitem__(self, key):
        return self.__dict__.setdefault("_properties", {})[key]


class FakeSockets:
    """Node sockets, reachable by name or index like Blender's."""

    def __init__(self):
        self.items = {}

    def __getitem__(self, key):
        return self.items.setdefault(key, SimpleNamespace(key=key, default_value=None))


class FakeNodes(list):
    def new(self, kind):
        node = SimpleNamespace(
            type=kind, inputs=FakeSockets(), outputs=FakeSockets(), location=None
        )
        self.append(node)
        return node

    def of(self, kind):
        return next(node for node in self if node.type == kind)


class FakeInterface:
    def __init__(self):
        self.items_tree = []

    def new_socket(self, name, in_out, socket_type, parent=None):
        item = SimpleNamespace(
            item_type="SOCKET",
            name=name,
            in_out=in_out,
            socket_type=socket_type,
            parent=parent,
            identifier="Socket_{0}".format(len(self.items_tree)),
        )
        self.items_tree.append(item)
        return item

    def new_panel(self, name, default_closed=False):
        item = SimpleNamespace(item_type="PANEL", name=name, default_closed=default_closed)
        self.items_tree.append(item)
        return item


class FakeLinks(list):
    def new(self, a, b):
        self.append((a, b))


class FakeTree(FakeIdProperties):
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind
        self.interface = FakeInterface()
        self.nodes = FakeNodes()
        self.links = FakeLinks()


class FakeNodeGroups(list):
    def new(self, name, kind):
        tree = FakeTree(name, kind)
        self.append(tree)
        return tree


class FakeInputs:
    """Blender 5 ``modifier.properties.inputs``: one attribute per socket."""

    def __getattr__(self, identifier):
        value = SimpleNamespace(value=None)
        setattr(self, identifier, value)
        return value


class FakeViewportSwitch:
    """``show_viewport`` that remembers every value written to it."""

    def __init__(self):
        self.shown_history = [True]

    @property
    def show_viewport(self):
        return self.shown_history[-1]

    @show_viewport.setter
    def show_viewport(self, value):
        self.shown_history.append(value)


class FakeModifier(FakeViewportSwitch):
    def __init__(self, name, kind):
        super().__init__()
        self.name = name
        self.type = kind
        self.node_group = None
        self.properties = SimpleNamespace(inputs=FakeInputs())

    def value(self, identifier):
        return getattr(self.properties.inputs, identifier).value


class FakeLegacyModifier(FakeIdProperties, FakeViewportSwitch):
    """Blender 4.x: modifier inputs are ID properties on the modifier."""

    def __init__(self, name, kind):
        FakeViewportSwitch.__init__(self)
        self.name = name
        self.type = kind
        self.node_group = None

    def value(self, identifier):
        return self[identifier]


class FakeModifiers(list):
    kind = FakeModifier

    def new(self, name, kind):
        modifier = self.kind(name, kind)
        self.append(modifier)
        return modifier


class FakeCurveObject:
    def __init__(self, name, points, has_faces, kind="CURVE"):
        self.name = name
        self.type = kind
        self.data = SimpleNamespace(points=points, has_faces=has_faces)
        self.matrix_world = FakeMatrix.identity()
        self.modifiers = FakeModifiers()
        self.open_meshes = 0

    def evaluated_get(self, _depsgraph):
        return self

    def to_mesh(self):
        self.open_meshes += 1
        return SimpleNamespace(
            vertices=[SimpleNamespace(co=FakeVector(p)) for p in self.data.points],
            polygons=[object()] if self.data.has_faces else [],
        )

    def to_mesh_clear(self):
        self.open_meshes -= 1


def fake_region(width=100, height=100, matrix=None, kind="WINDOW"):
    return SimpleNamespace(
        type=kind,
        width=width,
        height=height,
        data=SimpleNamespace(
            perspective_matrix=matrix if matrix is not None else FakeMatrix.identity()
        ),
    )


def fake_area(regions, width=100, height=100, kind="VIEW_3D"):
    return SimpleNamespace(type=kind, width=width, height=height, regions=regions)


class ProjectCurvesFromViewTests(unittest.TestCase):
    def setUp(self):
        # No ``objects``, ``meshes`` or ``collections``: the tool must not
        # create any datablock but its node group.
        self.bpy = SimpleNamespace(data=SimpleNamespace(node_groups=FakeNodeGroups()))
        self.module = load_blender_module(
            "blender_curve_uv.py", vector=FakeVector, bpy=self.bpy
        )
        self.viewport = fake_region()
        # The BlendMax menu runs from the top bar: no viewport in the context.
        self.context = SimpleNamespace(
            mode="OBJECT",
            selected_objects=[],
            area=fake_area([fake_region(kind="HEADER")], kind="TOPBAR"),
            region=fake_region(kind="HEADER"),
            screen=SimpleNamespace(areas=[fake_area([self.viewport])]),
            evaluated_depsgraph_get=lambda: object(),
        )

    def _curve(self, name="Logo", points=TRIANGLE, has_faces=True):
        return FakeCurveObject(name, points, has_faces)

    def _project(self, *selected):
        self.context.selected_objects = list(selected)
        return self.module.project_curves_from_view(self.context)

    def _ours(self, curve):
        found = [
            m for m in curve.modifiers
            if m.node_group is not None and m.node_group.get(GROUP_KEY)
        ]
        self.assertEqual(len(found), 1)
        return found[0]

    def _stored_rows(self, curve):
        modifier = self._ours(curve)
        ids = {
            item.name: item.identifier
            for item in modifier.node_group.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT"
        }
        return [
            [modifier.value(ids["Row {0} Column {1}".format(r + 1, c + 1)]) for c in range(4)]
            for r in range(4)
        ]

    def _uvs(self, curve):
        """The UVs Geometry Nodes would write: stored view, then divide by w."""
        rows = self._stored_rows(curve)
        uvs = []
        for x, y, z in curve.data.points:
            u, v, _depth, w = (r[0] * x + r[1] * y + r[2] * z + r[3] for r in rows)
            uvs.append((u / w, v / w))
        return uvs

    def test_adds_one_modifier_whose_stored_view_gives_project_from_view_uvs(self):
        curve = self._curve()

        result = self._project(curve)

        self.assertEqual(result.projected, (curve,))
        modifier = self._ours(curve)
        self.assertEqual(modifier.name, "BlendMax Curve UV")
        self.assertEqual(modifier.type, "NODES")
        self.assertEqual(self._uvs(curve), [(0.5, 0.5), (0.75, 0.5), (0.5, 0.75)])
        self.assertEqual(result.skipped, ())
        self.assertEqual(result.outside, 0)

    def test_curve_stays_the_same_curve_and_no_other_datablock_is_made(self):
        curve = self._curve()
        data = curve.data
        world = curve.matrix_world

        self._project(curve)

        self.assertEqual(curve.type, "CURVE")
        self.assertIs(curve.data, data)
        self.assertIs(curve.matrix_world, world)
        self.assertEqual(len(self.bpy.data.node_groups), 1)
        self.assertEqual(curve.open_meshes, 0)

    def test_node_group_writes_uvmap_on_face_corners_from_projected_positions(self):
        self._project(self._curve())

        group = self.bpy.data.node_groups[0]
        self.assertEqual(group.name, "BlendMax Curve UV")
        self.assertEqual(group.kind, "GeometryNodeTree")
        store = group.nodes.of("GeometryNodeStoreNamedAttribute")
        self.assertEqual(store.data_type, "FLOAT2")
        self.assertEqual(store.domain, "CORNER")
        self.assertEqual(store.inputs["Name"].default_value, "UVMap")
        project = group.nodes.of("FunctionNodeProjectPoint")
        combine = group.nodes.of("FunctionNodeCombineMatrix")
        position = group.nodes.of("GeometryNodeInputPosition")
        links = list(group.links)
        self.assertIn((position.outputs["Position"], project.inputs["Vector"]), links)
        self.assertIn((combine.outputs["Matrix"], project.inputs["Transform"]), links)
        self.assertIn((project.outputs["Vector"], store.inputs["Value"]), links)
        # Combine Matrix takes its inputs column by column.
        group_in = group.nodes.of("NodeGroupInput")
        self.assertIn(
            (group_in.outputs["Row 2 Column 1"], combine.inputs[1]), links
        )
        self.assertIn(
            (group_in.outputs["Row 1 Column 2"], combine.inputs[4]), links
        )

    def test_stored_view_sits_in_a_closed_panel(self):
        self._project(self._curve())

        items = self.bpy.data.node_groups[0].interface.items_tree
        panel = next(item for item in items if item.item_type == "PANEL")
        self.assertEqual(panel.name, "Stored View")
        self.assertTrue(panel.default_closed)
        view_inputs = [item for item in items if item.item_type == "SOCKET" and item.name.startswith("Row")]
        self.assertEqual(len(view_inputs), 16)
        self.assertTrue(all(item.parent is panel for item in view_inputs))

    def test_rerun_updates_the_same_modifier_from_a_new_view(self):
        curve = self._curve()
        self._project(curve)
        first = self._ours(curve)

        self.viewport.data.perspective_matrix = FakeMatrix.translation_scale(
            (0.25, 0.0, 0.0), (1, 1, 1)
        )
        self._project(curve)

        self.assertIs(self._ours(curve), first)
        self.assertEqual(len(curve.modifiers), 1)
        self.assertEqual(self._uvs(curve)[0], (0.625, 0.5))
        self.assertEqual(len(self.bpy.data.node_groups), 1)

    def test_every_run_flips_the_viewport_switch_and_restores_it(self):
        # Found in live use: without the flip, Material Preview kept drawing
        # the old UVs after a re-run although the Curve held the new ones.
        curve = self._curve()
        self._project(curve)
        modifier = self._ours(curve)
        self.assertEqual(modifier.shown_history, [True, False, True])

        modifier.show_viewport = False  # the user hides it in the viewport
        self._project(curve)

        self.assertEqual(modifier.shown_history[-3:], [False, True, False])

    def test_rerun_follows_a_resized_viewport(self):
        curve = self._curve()
        self._project(curve)

        self.viewport.width = 200
        self._project(curve)

        self.assertEqual(self._uvs(curve), [(0.5, 0.5), (0.75, 0.5), (0.5, 0.625)])

    def test_renamed_modifier_and_group_are_still_found(self):
        curve = self._curve()
        self._project(curve)
        self._ours(curve).name = "My UV"
        self.bpy.data.node_groups[0].name = "Renamed"

        self._project(curve)

        self.assertEqual(len(curve.modifiers), 1)
        self.assertEqual(len(self.bpy.data.node_groups), 1)

    def test_other_modifiers_are_left_alone_and_ours_goes_last(self):
        curve = self._curve()
        theirs = curve.modifiers.new("Their Nodes", "NODES")
        theirs.node_group = FakeTree("Theirs", "GeometryNodeTree")

        self._project(curve)

        self.assertIs(curve.modifiers[0], theirs)
        self.assertIs(curve.modifiers[1], self._ours(curve))
        self.assertEqual(theirs.node_group.name, "Theirs")

    def test_uses_the_curve_world_transform_as_the_projection_reference(self):
        curve = self._curve()
        curve.matrix_world = FakeMatrix.translation_scale((0.5, 0.0, 0.0), (1, 1, 1))

        self._project(curve)

        self.assertEqual(self._uvs(curve)[0], (0.75, 0.5))

    def test_every_selected_curve_shares_one_group_and_others_are_ignored(self):
        first = self._curve("L")
        second = self._curve("M")
        light = FakeCurveObject("Light", (), False, kind="LIGHT")

        result = self._project(first, light, second)

        self.assertEqual(result.projected, (first, second))
        self.assertEqual(len(self.bpy.data.node_groups), 1)
        self.assertIs(
            self._ours(first).node_group, self._ours(second).node_group
        )
        self.assertEqual(light.modifiers, [])

    def test_curve_without_faces_is_skipped_and_gets_no_modifier(self):
        filled = self._curve("Filled")
        line = self._curve("Line", has_faces=False)

        result = self._project(filled, line)

        self.assertEqual(result.skipped, ("Line",))
        self.assertEqual(result.projected, (filled,))
        self.assertEqual(line.modifiers, [])
        self.assertEqual(line.open_meshes, 0)

    def test_only_curves_without_faces_is_an_error_and_leaves_nothing(self):
        line = self._curve(has_faces=False)

        with self.assertRaisesRegex(ValueError, "no faces"):
            self._project(line)

        self.assertEqual(line.modifiers, [])
        self.assertEqual(self.bpy.data.node_groups, [])

    def test_vertices_outside_the_view_are_reported(self):
        curve = self._curve(points=((5.0, 0.0, 0.0),))

        result = self._project(curve)

        self.assertEqual(result.outside, 1)
        self.assertEqual(self._uvs(curve), [(3.0, 0.5)])

    def test_edit_mode_is_refused_and_changes_nothing(self):
        curve = self._curve()

        for mode in ("EDIT_CURVE", "EDIT_MESH", "SCULPT"):
            with self.subTest(mode=mode):
                self.context.mode = mode
                with self.assertRaisesRegex(ValueError, "Switch to Object Mode"):
                    self._project(curve)
                self.assertEqual(curve.modifiers, [])
                self.assertEqual(self.bpy.data.node_groups, [])

    def test_no_selection_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Select one or more Curve"):
            self._project()

    def test_non_curve_selection_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Select one or more Curve"):
            self._project(FakeCurveObject("Cube", (), True, kind="MESH"))

    def test_blender_4_modifier_inputs_are_written_as_id_properties(self):
        curve = self._curve()
        curve.modifiers.kind = FakeLegacyModifier

        self._project(curve)

        self.assertEqual(self._uvs(curve), [(0.5, 0.5), (0.75, 0.5), (0.5, 0.75)])

    def test_top_bar_run_uses_the_largest_viewport_on_the_screen(self):
        small = fake_region(width=999)
        large = fake_region(width=200)
        self.context.screen.areas = [
            fake_area([fake_region()], width=2000, height=2000, kind="IMAGE_EDITOR"),
            fake_area([small], width=10, height=10),
            fake_area([large], width=200, height=100),
        ]
        curve = self._curve()

        self._project(curve)

        # A region 200 wide and 100 high halves V: 0.75 becomes 0.625.
        self.assertEqual(self._uvs(curve)[2], (0.5, 0.625))

    def test_run_from_inside_a_viewport_uses_that_viewport(self):
        here = fake_region(width=200)
        self.context.area = fake_area([here], width=1, height=1)
        self.context.region = here
        curve = self._curve()

        self._project(curve)

        self.assertEqual(self._uvs(curve)[2], (0.5, 0.625))

    def test_screen_without_a_viewport_is_an_error_and_creates_nothing(self):
        self.context.screen.areas = [fake_area([], kind="IMAGE_EDITOR")]
        curve = self._curve()

        with self.assertRaisesRegex(ValueError, "Open a 3D Viewport"):
            self._project(curve)

        self.assertEqual(curve.modifiers, [])
        self.assertEqual(self.bpy.data.node_groups, [])

    def test_background_run_without_a_screen_is_an_error(self):
        self.context.screen = None
        self.context.area = None
        self.context.region = None

        with self.assertRaisesRegex(ValueError, "Open a 3D Viewport"):
            self._project(self._curve())

    def test_collapsed_viewport_is_an_error_and_creates_nothing(self):
        self.viewport.height = 0
        curve = self._curve()

        with self.assertRaisesRegex(ValueError, "no usable size"):
            self._project(curve)

        self.assertEqual(curve.modifiers, [])


if __name__ == "__main__":
    unittest.main()
