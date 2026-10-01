"""Blender-side contract tests for the Measurement Cage tool module.

``blender_presentation`` runs against a small fake ``bpy``: a scene
collection, one presentation collection, mesh/curve datablocks with user
counts, and the object/property surface the module touches. The geometry
math itself lives in ``test_presentation_cage.py``; these tests cover the
Blender glue: datablock ownership, the remove teardown, source fallback and
re-targeting, and label reuse by custom property.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from blendmax_blender.presentation_cage import cage_geometry

try:
    from fakes import FakeMatrix, FakeVector, load_blender_module
except ImportError:  # dotted-module invocation from the repository root
    from tests.fakes import FakeMatrix, FakeVector, load_blender_module


_CUBE_CORNERS = (
    (-0.5, -0.5, -0.5),
    (0.5, -0.5, -0.5),
    (0.5, 0.5, -0.5),
    (-0.5, 0.5, -0.5),
    (-0.5, -0.5, 0.5),
    (0.5, -0.5, 0.5),
    (0.5, 0.5, 0.5),
    (-0.5, 0.5, 0.5),
)


class FakeSplinePoints(list):
    def add(self, count):
        self.extend(SimpleNamespace(co=None) for _ in range(count))


class FakeSpline:
    def __init__(self):
        self.points = FakeSplinePoints([SimpleNamespace(co=None)])


class FakeSplines(list):
    def new(self, kind):
        spline = FakeSpline()
        self.append(spline)
        return spline

    def remove(self, spline):
        super().remove(spline)


class FakeMaterials(list):
    def clear(self):
        for material in self:
            material.users -= 1
        super().clear()

    def append(self, material):
        if material not in self:
            material.users += 1
            super().append(material)


class FakeDataBlock:
    """Mesh/curve datablock with Blender's user-count semantics."""

    def __init__(self, name, kind):
        self.name = name
        self.kind = kind
        self.users = 0
        self.vertices = []
        self.edges = []
        self.faces = []
        self.from_pydata_calls = []
        self.splines = FakeSplines()
        self.materials = FakeMaterials()
        self.dimensions = None
        self.resolution_u = 0
        self.bevel_depth = 0.0
        self.bevel_resolution = 0
        self.body = ""
        self.align_x = None
        self.align_y = None
        self.size = 0.0

    def clear_geometry(self):
        self.vertices = []
        self.edges = []
        self.faces = []

    def from_pydata(self, vertices, edges, faces):
        self.from_pydata_calls.append((list(vertices), list(edges), list(faces)))
        self.vertices = list(vertices)
        self.edges = list(edges)
        self.faces = list(faces)

    def update(self):
        pass

    def update_tag(self):
        pass


class FakeDataManager(list):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def new(self, name, type=None):
        datablock = FakeDataBlock(name, type or self.kind)
        self.append(datablock)
        return datablock

    def get(self, name):
        return next((item for item in self if item.name == name), None)

    def remove(self, item):
        for material in tuple(getattr(item, "materials", ())):
            material.users -= 1
        list.remove(self, item)


class FakeInput:
    def __init__(self, value):
        self.default_value = value


class FakePrincipled:
    def __init__(self):
        self.inputs = {
            "Base Color": FakeInput((0.0, 0.0, 0.0, 1.0)),
            "Roughness": FakeInput(0.0),
        }


class FakeNodes(dict):
    def __init__(self):
        super().__init__({"Principled BSDF": FakePrincipled()})


class FakeMaterial:
    def __init__(self, name):
        self.name = name
        self.users = 0
        self.diffuse_color = None
        self.use_nodes = False
        self.node_tree = SimpleNamespace(nodes=FakeNodes())
        self._properties = {}

    def get(self, key, default=None):
        return self._properties.get(key, default)

    def __setitem__(self, key, value):
        self._properties[key] = value


class FakeMaterialManager(list):
    def new(self, name):
        material = FakeMaterial(name)
        self.append(material)
        return material


class FakeObject:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        if data is not None:
            data.users += 1
        self.type = data.kind if data is not None else "EMPTY"
        self.users_collection = []
        self.children = []
        self.hide_render = False
        self.show_in_front = False
        self.display_type = "TEXTURED"
        self.hide_viewport = False
        self.selected = False
        self.location = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.rotation_mode = "XYZ"
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.delta_location = (0.0, 0.0, 0.0)
        self.delta_rotation_euler = (0.0, 0.0, 0.0)
        self.delta_scale = (1.0, 1.0, 1.0)
        self.parent = None
        self.bound_box = _CUBE_CORNERS
        self._properties = {}

    @property
    def matrix_world(self):
        return FakeMatrix.translation_scale(self.location, (1.0, 1.0, 1.0))

    def get(self, key, default=None):
        return self._properties.get(key, default)

    def __setitem__(self, key, value):
        self._properties[key] = value

    def __getitem__(self, key):
        return self._properties[key]

    def pop(self, key, default=None):
        return self._properties.pop(key, default)

    def hide_set(self, state):
        self.hide_viewport = bool(state)

    def select_set(self, state):
        self.selected = bool(state)


class FakeObjectManager(list):
    def new(self, name, data):
        obj = FakeObject(name, data)
        self.append(obj)
        return obj

    def remove(self, obj, do_unlink=True):
        if do_unlink:
            for collection in tuple(obj.users_collection):
                collection.objects.unlink(obj)
        if obj.data is not None:
            obj.data.users -= 1
        list.remove(self, obj)

    def get(self, name):
        return next((item for item in self if item.name == name), None)


class FakeCollectionObjects(list):
    def __init__(self, collection):
        super().__init__()
        self.collection = collection

    def link(self, obj):
        if obj not in self:
            self.append(obj)
        if self.collection not in obj.users_collection:
            obj.users_collection.append(self.collection)

    def unlink(self, obj):
        if obj in self:
            self.remove(obj)
        if self.collection in obj.users_collection:
            obj.users_collection.remove(self.collection)


class FakeChildren(list):
    def link(self, item):
        if not any(existing is item for existing in self):
            self.append(item)

    def unlink(self, item):
        for index, existing in enumerate(self):
            if existing is item:
                del self[index]
                break


class FakeBpyPropCollection(FakeChildren):
    """Model bpy_prop_collection iteration and its name-only membership API."""

    def __contains__(self, value):
        if isinstance(value, str):
            return any(item.name == value for item in self)
        if isinstance(value, tuple) and all(isinstance(name, str) for name in value):
            return any(item.name in value for item in self)
        raise TypeError("bpy_prop_collection membership expects a name string")


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.objects = FakeCollectionObjects(self)
        self.children = FakeChildren()
        self._properties = {}

    def get(self, key, default=None):
        return self._properties.get(key, default)

    def __setitem__(self, key, value):
        self._properties[key] = value

    def as_pointer(self):
        return id(self)


class FakeCollectionManager(list):
    def new(self, name):
        collection = FakeCollection(name)
        self.append(collection)
        return collection


class FakeBpyData:
    def __init__(self):
        self.meshes = FakeDataManager("MESH")
        self.curves = FakeDataManager("FONT")
        self.objects = FakeObjectManager()
        self.collections = FakeCollectionManager()
        self.materials = FakeMaterialManager()
        self.scenes = []


class FakeBpy:
    """Just enough ``bpy`` for the Measurement Cage tool module."""

    def __init__(self):
        self.data = FakeBpyData()
        self.scene = SimpleNamespace(collection=FakeCollection("Scene Collection"))
        self.data.scenes.append(self.scene)
        self.scene_collection = self.scene.collection


class MeasurementCageToolTests(unittest.TestCase):
    def setUp(self):
        self.bpy = FakeBpy()
        self.context = SimpleNamespace(
            scene=self.bpy.scene,
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=None)),
            selected_objects=[],
        )
        self.module = load_blender_module(
            "blender_presentation.py", vector=FakeVector, bpy=self.bpy
        )

    def _add_source(self, name, location=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
        mesh = self.bpy.data.meshes.new(name)
        mesh.vertices = [(0.0, 0.0, 0.0)]
        obj = self.bpy.data.objects.new(name, mesh)
        obj.location = location
        obj.bound_box = tuple(
            tuple(value * factor for value, factor in zip(corner, scale))
            for corner in _CUBE_CORNERS
        )
        return obj

    def _create(self, **kwargs):
        return self.module.create_measurement_cage(self.context, **kwargs)

    def _tool_objects(self, kind=None):
        return [
            obj
            for obj in self.bpy.data.objects
            if obj.get("blendmax_presentation_tool") == "measurement_cage"
            and (kind is None or obj.get("blendmax_presentation_kind") == kind)
        ]

    def test_cage_is_renderable_beveled_curve_lattice(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        cage, envelope = self._create(
            envelope_increment=0.5,
            divisions=(2, 1, 1),
        )

        self.assertEqual(envelope.dimensions, (1.0, 1.0, 1.0))
        self.assertIs(cage.data, self.bpy.data.curves.get("BlendMax Measurement Cage"))
        expected_vertices, expected_edges = cage_geometry(
            (envelope.minimum, envelope.maximum),
            (2, 1, 1),
        )
        actual_rods = {
            tuple(sorted(tuple(point.co[:3]) for point in spline.points))
            for spline in cage.data.splines
        }
        expected_rods = {
            tuple(sorted((expected_vertices[start], expected_vertices[end])))
            for start, end in expected_edges
        }
        self.assertEqual(actual_rods, expected_rods)
        self.assertEqual(len(cage.data.splines), len(actual_rods))
        self.assertEqual(cage.type, "CURVE")
        self.assertFalse(cage.hide_render)
        self.assertGreater(cage.data.bevel_depth, 0.0)
        self.assertEqual(cage.data.dimensions, "3D")
        self.assertEqual(len(cage.data.materials), 1)
        self.assertEqual(
            cage.data.materials[0].get("blendmax_measurement_material"), "cage"
        )
        self.assertEqual(cage.display_type, "SOLID")
        self.assertTrue(cage.show_in_front)
        self.assertFalse(cage.hide_viewport)
        self.assertEqual(cage["blendmax_measurement_envelope_increment"], 0.5)
        self.assertEqual(cage["blendmax_measurement_divisions"], (2, 1, 1))
        self.assertEqual(cage["blendmax_measurement_dimensions"], (1.0, 1.0, 1.0))
        self.assertEqual(cage["blendmax_measurement_asset_dimensions"], (1.0, 1.0, 1.0))
        self.assertEqual(cage["blendmax_measurement_source"], "Chair")

    def test_cage_and_labels_live_in_the_presentation_collection(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        self._create()

        self.assertEqual(len(self.bpy.data.collections), 1)
        collection = self.bpy.data.collections[0]
        self.assertEqual(
            collection.get("blendmax_presentation_collection"), "presentation"
        )
        self.assertIn(collection, self.bpy.scene_collection.children)
        tool_objects = self._tool_objects()
        self.assertEqual(len(tool_objects), 4)
        for obj in tool_objects:
            self.assertIn(collection, obj.users_collection)

    def test_single_selected_child_with_parent_uses_scene_root_collection(self):
        parent = self.bpy.data.objects.new("Hierarchy Parent", None)
        source = self._add_source("Single Child")
        source.parent = parent
        parent.children.append(source)
        parent_collection = self.bpy.data.collections.new("Asset Group")
        self.bpy.scene_collection.children.link(parent_collection)
        parent_collection.objects.link(parent)
        parent_collection.objects.link(source)
        self.context.selected_objects = [source]

        self._create(show_dimensions=False)

        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        self.assertIn(presentation, self.bpy.scene_collection.children)
        self.assertNotIn(presentation, parent_collection.children)
        self.assertIs(source.parent, parent)
        self.assertIsNone(self._tool_objects(kind="cage")[0].parent)

    def test_multiple_selection_uses_scene_root_not_source_collections(self):
        first = self._add_source("First")
        second = self._add_source("Second", location=(3.0, 0.0, 0.0))
        first_collection = self.bpy.data.collections.new("First Collection")
        second_collection = self.bpy.data.collections.new("Second Collection")
        self.bpy.scene_collection.children.link(first_collection)
        self.bpy.scene_collection.children.link(second_collection)
        first_collection.objects.link(first)
        second_collection.objects.link(second)
        self.context.selected_objects = [first, second]

        self._create(show_dimensions=False)

        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        self.assertIn(presentation, self.bpy.scene_collection.children)
        self.assertNotIn(presentation, first_collection.children)
        self.assertNotIn(presentation, second_collection.children)

    def test_selected_hierarchy_root_places_presentation_in_its_collection(self):
        hierarchy_collection = self.bpy.data.collections.new("BOOTH_ROOT")
        self.bpy.scene_collection.children.link(hierarchy_collection)
        root = self.bpy.data.objects.new("BOOTH_ROOT", None)
        child = self._add_source("Child_A", location=(2.0, 0.0, 0.0))
        root.location = (3.0, 4.0, 5.0)
        child.parent = root
        root.children.append(child)
        hierarchy_collection.objects.link(root)
        hierarchy_collection.objects.link(child)
        self.context.selected_objects = [root]
        before = (root.location, child.location, child.parent)

        self._create()

        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        self.assertIn(presentation, hierarchy_collection.children)
        self.assertNotIn(presentation, self.bpy.scene_collection.children)
        generated = self._tool_objects()
        self.assertEqual(len(generated), 4)
        self.assertTrue(all(obj in presentation.objects for obj in generated))
        self.assertTrue(all(obj.parent is None for obj in generated))
        self.assertEqual((root.location, child.location, child.parent), before)

        self.module.remove_measurement_cage(self.context)

        self.assertNotIn(presentation, self.bpy.data.collections)
        self.assertNotIn(presentation, hierarchy_collection.children)

    def test_hierarchy_placement_skips_off_scene_membership_for_reachable_collection(self):
        off_scene = self.bpy.data.collections.new("Off Scene")
        reachable = self.bpy.data.collections.new("Active Hierarchy")
        self.bpy.scene_collection.children.link(reachable)
        root = self.bpy.data.objects.new("Root", None)
        child = self._add_source("Child")
        child.parent = root
        root.children.append(child)
        off_scene.objects.link(root)
        reachable.objects.link(root)
        reachable.objects.link(child)
        self.context.selected_objects = [root]

        self._create(show_dimensions=False)

        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        self.assertEqual(root.users_collection, [off_scene, reachable])
        self.assertIn(presentation, reachable.children)
        self.assertNotIn(presentation, off_scene.children)

    def test_hierarchy_placement_falls_back_to_scene_when_no_membership_is_reachable(self):
        off_scene = self.bpy.data.collections.new("Off Scene")
        root = self.bpy.data.objects.new("Root", None)
        child = self._add_source("Child")
        child.parent = root
        root.children.append(child)
        off_scene.objects.link(root)
        off_scene.objects.link(child)
        self.context.selected_objects = [root]

        self._create(show_dimensions=False)

        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        self.assertIn(presentation, self.bpy.scene_collection.children)
        self.assertNotIn(presentation, off_scene.children)

    def test_presentation_collection_moves_when_selection_mode_changes(self):
        root_collection = self.bpy.data.collections.new("Root Collection")
        self.bpy.scene_collection.children.link(root_collection)
        root = self.bpy.data.objects.new("Root", None)
        source = self._add_source("Child")
        source.parent = root
        root.children.append(source)
        root_collection.objects.link(root)
        root_collection.objects.link(source)
        self.context.selected_objects = [root]
        self._create(show_dimensions=False)
        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )

        self.context.selected_objects = [source]
        self.context.view_layer.objects.active = source
        self._create(show_dimensions=False)

        self.assertIn(presentation, self.bpy.scene_collection.children)
        self.assertNotIn(presentation, root_collection.children)
        self.assertEqual(
            sum(
                item.get("blendmax_presentation_collection") == "presentation"
                for item in self.bpy.data.collections
            ),
            1,
        )

    def test_relocation_unlinks_presentation_from_other_scene_master_collections(self):
        source = self._add_source("Shared Source")
        scene_a = self.context.scene
        scene_b = SimpleNamespace(
            collection=FakeCollection("Scene B Collection")
        )
        self.bpy.data.scenes.append(scene_b)
        scene_a.collection.objects.link(source)
        scene_b.collection.objects.link(source)
        self.context.selected_objects = [source]

        cage, _ = self._create(show_dimensions=False)
        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )
        generated_before = tuple(self._tool_objects())
        self.assertIn(presentation, scene_a.collection.children)

        self.context.scene = scene_b
        self.context.view_layer.objects.active = source
        self._create(show_dimensions=False)

        self.assertNotIn(presentation, scene_a.collection.children)
        self.assertIn(presentation, scene_b.collection.children)
        self.assertEqual(tuple(self._tool_objects()), generated_before)
        self.assertIs(self._tool_objects(kind="cage")[0], cage)

    def test_collection_membership_uses_blender_rna_identity_contract(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        cage, _ = self._create()
        presentation = next(
            item
            for item in self.bpy.data.collections
            if item.get("blendmax_presentation_collection") == "presentation"
        )

        old_parent = FakeCollection("Previous Parent")
        old_parent.children.link(presentation)
        self.bpy.data.collections.append(old_parent)
        self.bpy.scene_collection.children.unlink(presentation)

        # bpy_prop_collection raises TypeError for RNA objects passed to `in`.
        old_parent.children = FakeBpyPropCollection(old_parent.children)
        self.bpy.scene_collection.children = FakeBpyPropCollection(
            self.bpy.scene_collection.children
        )
        for obj in self._tool_objects():
            obj.users_collection = FakeBpyPropCollection(obj.users_collection)

        updated_cage, _ = self._create()

        self.assertIs(updated_cage, cage)
        self.assertTrue(
            any(item is presentation for item in self.bpy.scene_collection.children)
        )
        self.assertFalse(any(item is presentation for item in old_parent.children))

    def test_source_transforms_and_hierarchy_are_unchanged(self):
        parent = self._add_source("Parent")
        source = self._add_source("Chair", location=(2.0, -1.0, 4.0))
        source.scale = (1.5, 2.0, 0.75)
        source.rotation_euler = (0.25, -0.5, 1.0)
        source.parent = parent
        parent.children.append(source)
        self.context.selected_objects = [source]
        before = (
            source.location,
            source.rotation_euler,
            source.scale,
            source.parent,
            tuple(parent.children),
        )

        self._create()

        self.assertEqual(
            (
                source.location,
                source.rotation_euler,
                source.scale,
                source.parent,
                tuple(parent.children),
            ),
            before,
        )

    def test_source_without_valid_mesh_geometry_fails_before_creating_cage(self):
        source = self._add_source("Empty Mesh")
        source.data.vertices = []
        self.context.selected_objects = [source]

        with self.assertRaisesRegex(ValueError, "no valid mesh geometry"):
            self._create()

        self.assertEqual(self._tool_objects(), [])
        self.assertEqual(list(self.bpy.data.collections), [])

    def test_invalid_increment_is_rejected_before_creating_cage(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        with self.assertRaisesRegex(ValueError, "finite positive"):
            self._create(envelope_increment=0.0)

        self.assertEqual(self._tool_objects(), [])
        self.assertEqual(list(self.bpy.data.collections), [])

    def test_labels_and_metadata_report_standardized_envelope_dimensions(self):
        source = self._add_source("Display", scale=(3.6, 2.5, 1.5))
        self.context.selected_objects = [source]

        cage, envelope = self._create(envelope_increment=1.0)

        self.assertEqual(envelope.dimensions, (4.0, 3.0, 2.0))
        self.assertEqual(
            cage["blendmax_measurement_asset_dimensions"],
            (3.6, 2.5, 1.5),
        )
        self.assertEqual(cage["blendmax_measurement_dimensions"], (4.0, 3.0, 2.0))
        labels = {
            obj.get("blendmax_measurement_dimension"): obj.data.body
            for obj in self._tool_objects(kind="label")
        }
        self.assertEqual(labels["Width"], "W 4.000 m")
        self.assertEqual(labels["Depth"], "D 3.000 m")
        self.assertEqual(labels["Height"], "H 2.000 m")

    def test_multiple_selected_objects_use_one_combined_cage_including_gaps(self):
        left = self._add_source("Left", location=(0.0, 0.0, 0.0), scale=(2.0, 1.0, 1.0))
        right = self._add_source("Right", location=(5.0, 0.0, 0.0), scale=(2.0, 1.0, 1.0))
        self.context.selected_objects = [left, right]

        cage, envelope = self._create(envelope_increment=1.0, show_dimensions=False)

        self.assertEqual(envelope.minimum, (-1.0, -0.5, -0.5))
        self.assertEqual(envelope.dimensions, (7.0, 1.0, 1.0))
        self.assertEqual(len(self._tool_objects(kind="cage")), 1)
        self.assertEqual(cage["blendmax_measurement_sources"], '["Left", "Right"]')
        self.assertTrue(left.selected)
        self.assertTrue(right.selected)

    def test_selected_hierarchy_includes_grandchildren_and_deeper_descendants(self):
        root = self.bpy.data.objects.new("Root", None)
        child = self._add_source("Child", location=(2.0, 0.0, 0.0))
        grandchild = self.bpy.data.objects.new("Grandchild", None)
        great_grandchild = self._add_source("Great Grandchild", location=(8.0, 0.0, 0.0))
        child.parent = root
        root.children.append(child)
        grandchild.parent = child
        child.children.append(grandchild)
        great_grandchild.parent = grandchild
        grandchild.children.append(great_grandchild)
        self.context.selected_objects = [root]

        _cage, envelope = self._create(envelope_increment=1.0, show_dimensions=False)

        self.assertEqual(envelope.minimum, (1.5, -0.5, -0.5))
        self.assertEqual(envelope.dimensions, (7.0, 1.0, 1.0))

    def test_active_cage_restores_multiple_source_roots_for_rerun(self):
        first = self._add_source("First")
        second = self._add_source("Second", location=(4.0, 0.0, 0.0))
        self.context.selected_objects = [first, second]
        cage, first_envelope = self._create(show_dimensions=False)

        self.context.selected_objects = [cage]
        self.context.view_layer.objects.active = cage
        _same_cage, rerun_envelope = self._create(show_dimensions=False)

        self.assertEqual(first_envelope, rerun_envelope)
        self.assertEqual(self.context.view_layer.objects.active, first)
        self.assertTrue(first.selected)
        self.assertTrue(second.selected)
        self.assertEqual(len(self._tool_objects(kind="cage")), 1)

    def test_rerun_updates_the_same_cage_and_labels(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        first_cage, _ = self._create()
        first_cage["blendmax_measurement_margin"] = 0.25
        object_count = len(self.bpy.data.objects)
        mesh_count = len(self.bpy.data.meshes)
        curve_count = len(self.bpy.data.curves)

        second_cage, _ = self._create()

        self.assertIs(first_cage, second_cage)
        self.assertEqual(len(self.bpy.data.objects), object_count)
        self.assertEqual(len(self.bpy.data.meshes), mesh_count)
        self.assertEqual(len(self.bpy.data.curves), curve_count)
        self.assertNotIn("blendmax_measurement_margin", first_cage._properties)

    def test_rerun_removes_an_existing_duplicate_cage(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        cage, _ = self._create(show_dimensions=False)
        collection = self.bpy.data.collections[0]
        duplicate_data = self.bpy.data.curves.new("Duplicate Cage", type="CURVE")
        duplicate = self.bpy.data.objects.new("Duplicate Cage", duplicate_data)
        duplicate["blendmax_presentation_tool"] = "measurement_cage"
        duplicate["blendmax_presentation_kind"] = "cage"
        collection.objects.link(duplicate)

        updated, _ = self._create(show_dimensions=False)

        self.assertIs(updated, cage)
        self.assertEqual(self._tool_objects(kind="cage"), [cage])
        self.assertNotIn(duplicate_data, self.bpy.data.curves)

    def test_rerun_resets_cage_and_label_transforms_to_world_space(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        cage, _ = self._create()
        labels = self._tool_objects(kind="label")

        cage.location = (10.0, -4.0, 2.0)
        cage.rotation_euler = (0.5, 0.25, -0.75)
        cage.scale = (2.0, 3.0, 4.0)
        cage.delta_location = (1.0, 2.0, 3.0)
        cage.delta_rotation_euler = (0.1, 0.2, 0.3)
        cage.delta_scale = (2.0, 2.0, 2.0)
        cage.parent = source
        for label in labels:
            label.location = (20.0, 30.0, 40.0)
            label.scale = (2.0, 2.0, 2.0)
            label.delta_location = (1.0, 2.0, 3.0)
            label.parent = source

        self._create()

        self.assertIsNone(cage.parent)
        self.assertEqual(cage.location, (0.0, 0.0, 0.0))
        self.assertEqual(cage.rotation_euler, (0.0, 0.0, 0.0))
        self.assertEqual(cage.scale, (1.0, 1.0, 1.0))
        self.assertEqual(cage.delta_location, (0.0, 0.0, 0.0))
        self.assertEqual(cage.delta_rotation_euler, (0.0, 0.0, 0.0))
        self.assertEqual(cage.delta_scale, (1.0, 1.0, 1.0))
        vertices, edges = cage_geometry(
            ((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
        )
        actual_rods = {
            tuple(sorted(tuple(point.co[:3]) for point in spline.points))
            for spline in cage.data.splines
        }
        expected_rods = {
            tuple(sorted((vertices[start], vertices[end]))) for start, end in edges
        }
        self.assertEqual(actual_rods, expected_rods)
        for label in labels:
            self.assertIsNone(label.parent)
            self.assertNotEqual(label.location, (20.0, 30.0, 40.0))
            self.assertEqual(label.scale, (1.0, 1.0, 1.0))
            self.assertEqual(label.delta_location, (0.0, 0.0, 0.0))

    def test_dimension_labels_carry_the_dimension_property(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        self._create()

        labels = {
            obj.get("blendmax_measurement_dimension"): obj
            for obj in self._tool_objects(kind="label")
        }
        self.assertEqual(set(labels), {"Width", "Depth", "Height"})
        for dimension, label in labels.items():
            self.assertTrue(label.data.body.startswith(dimension[0] + " "))
            self.assertFalse(label.hide_render)

    def test_renamed_label_is_reused_instead_of_duplicated(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        self._create()
        width_label = next(
            obj
            for obj in self._tool_objects(kind="label")
            if obj.get("blendmax_measurement_dimension") == "Width"
        )
        width_label.name = "My Width Label"
        object_count = len(self.bpy.data.objects)
        curve_count = len(self.bpy.data.curves)

        self._create()

        self.assertEqual(len(self.bpy.data.objects), object_count)
        self.assertEqual(len(self.bpy.data.curves), curve_count)
        self.assertEqual(
            [
                obj.name
                for obj in self._tool_objects(kind="label")
                if obj.get("blendmax_measurement_dimension") == "Width"
            ],
            ["My Width Label"],
        )
        self.assertFalse(width_label.hide_viewport)

    def test_labels_are_hidden_but_reused_when_dimensions_are_disabled(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        self._create()
        labels = self._tool_objects(kind="label")
        curve_count = len(self.bpy.data.curves)

        self._create(show_dimensions=False)

        self.assertEqual(len(self.bpy.data.curves), curve_count)
        self.assertTrue(all(label.hide_viewport for label in labels))
        self.assertTrue(all(label.hide_render for label in labels))

        self._create(show_dimensions=True)

        self.assertEqual(len(self.bpy.data.curves), curve_count)
        self.assertFalse(any(label.hide_viewport for label in labels))
        self.assertFalse(any(label.hide_render for label in labels))

    def test_current_multiple_selection_replaces_the_stored_source_roots(self):
        source_a = self._add_source("Chair")
        self.context.selected_objects = [source_a]
        cage, _ = self._create()
        source_b = self._add_source(
            "Bench", location=(5.0, 0.0, 0.0), scale=(2.0, 2.0, 2.0)
        )

        self.context.selected_objects = [source_b, source_a]
        self.context.view_layer.objects.active = cage
        self._create()

        self.assertEqual(cage["blendmax_measurement_source"], "Bench")
        self.assertEqual(cage["blendmax_measurement_sources"], '["Bench", "Chair"]')
        self.assertEqual(cage["blendmax_measurement_dimensions"], (7.0, 2.0, 2.0))

    def test_cage_re_targets_the_selection_when_stored_source_is_deleted(self):
        source_a = self._add_source("Chair")
        self.context.selected_objects = [source_a]
        cage, _ = self._create()
        self.bpy.data.objects.remove(source_a, do_unlink=True)
        source_b = self._add_source(
            "Bench", location=(5.0, 0.0, 0.0), scale=(2.0, 2.0, 2.0)
        )

        self.context.selected_objects = [cage, source_b]
        self.context.view_layer.objects.active = cage
        self._create()

        self.assertEqual(cage["blendmax_measurement_source"], "Bench")
        self.assertEqual(cage["blendmax_measurement_dimensions"], (2.0, 2.0, 2.0))

    def test_cage_re_targets_the_selection_when_stored_source_was_renamed(self):
        source_a = self._add_source("Chair")
        self.context.selected_objects = [source_a]
        cage, _ = self._create()
        source_a.name = "Dining Chair"
        source_b = self._add_source(
            "Bench", location=(5.0, 0.0, 0.0), scale=(2.0, 2.0, 2.0)
        )

        self.context.selected_objects = [source_b]
        self.context.view_layer.objects.active = cage
        self._create()

        self.assertEqual(cage["blendmax_measurement_source"], "Bench")

    def test_cage_active_without_any_usable_source_still_fails(self):
        source_a = self._add_source("Chair")
        self.context.selected_objects = [source_a]
        cage, _ = self._create()
        self.bpy.data.objects.remove(source_a, do_unlink=True)

        self.context.selected_objects = [cage]
        self.context.view_layer.objects.active = cage
        with self.assertRaises(ValueError):
            self._create()

    def test_remove_measurement_cage_frees_datablocks_and_collection(self):
        source = self._add_source("Chair")
        self.context.selected_objects = [source]
        self._create()
        cage_curve = self.bpy.data.curves.get("BlendMax Measurement Cage")
        label_curves = list(self.bpy.data.curves)

        removed = self.module.remove_measurement_cage(self.context)

        self.assertEqual(removed, 4)
        self.assertNotIn(cage_curve, self.bpy.data.curves)
        self.assertEqual(list(self.bpy.data.curves), [])
        self.assertEqual(list(self.bpy.data.materials), [])
        self.assertEqual(label_curves[0].users, 0)
        self.assertEqual(list(self.bpy.data.collections), [])
        self.assertIsNone(self.bpy.data.objects.get("BlendMax Measurement Cage"))
        self.assertEqual(list(self.bpy.data.objects), [source])

    def test_remove_without_a_cage_is_a_no_op(self):
        self.assertEqual(self.module.remove_measurement_cage(self.context), 0)
        self.assertEqual(list(self.bpy.data.collections), [])

    def test_recreating_a_non_mesh_cage_frees_the_stale_datablock(self):
        collection = self.bpy.data.collections.new("BlendMax Presentation")
        collection["blendmax_presentation_collection"] = "presentation"
        self.bpy.scene_collection.children.link(collection)
        stale_curve = self.bpy.data.curves.new(
            "BlendMax Measurement Cage", type="FONT"
        )
        corrupt_cage = self.bpy.data.objects.new(
            "BlendMax Measurement Cage", stale_curve
        )
        corrupt_cage["blendmax_presentation_tool"] = "measurement_cage"
        corrupt_cage["blendmax_presentation_kind"] = "cage"
        collection.objects.link(corrupt_cage)

        source = self._add_source("Chair")
        self.context.selected_objects = [source]

        cage, _ = self._create()

        self.assertIsNot(cage, corrupt_cage)
        self.assertEqual(cage.type, "CURVE")
        self.assertNotIn(stale_curve, self.bpy.data.curves)
        self.assertIsNotNone(self.bpy.data.curves.get("BlendMax Measurement Cage"))
        self.assertNotIn(corrupt_cage, self.bpy.data.objects)


if __name__ == "__main__":
    unittest.main()
