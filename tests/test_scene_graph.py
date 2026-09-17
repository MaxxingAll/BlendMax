"""Focused tests for the shared scene-graph helpers.

These pin the behaviour that :mod:`blendmax_max.validation` and
:mod:`blendmax_max.cleanup` relied on before the helpers were extracted, so the
extraction can be shown to be behaviour-preserving rather than merely green.
"""

from __future__ import annotations

import unittest

from blendmax_max.models import SceneNode
from blendmax_max.scene_graph import (
    descendant_ids,
    has_group_ancestor,
    is_geometry,
)


def node(
    node_id,
    parent_id=None,
    *,
    superclass="GeometryClass",
    group_head=False,
):
    return SceneNode(
        node_id=node_id,
        name=node_id,
        node_type="Editable_Poly",
        superclass=superclass,
        parent_id=parent_id,
        is_group_head=group_head,
        is_group_member=not group_head,
    )


def by_id(nodes):
    return {item.node_id: item for item in nodes}


class DescendantIdsTests(unittest.TestCase):
    def test_nested_descendants_are_all_returned(self):
        nodes = [node("root"), node("a", "root"), node("b", "a"), node("c", "b")]

        self.assertEqual(descendant_ids("root", nodes), {"a", "b", "c"})

    def test_root_is_excluded_from_its_own_descendants(self):
        nodes = [node("root"), node("a", "root")]

        self.assertNotIn("root", descendant_ids("root", nodes))

    def test_leaf_has_no_descendants(self):
        nodes = [node("root"), node("leaf", "root")]

        self.assertEqual(descendant_ids("leaf", nodes), set())

    def test_unknown_root_returns_empty(self):
        nodes = [node("root"), node("a", "root")]

        self.assertEqual(descendant_ids("missing", nodes), set())

    def test_siblings_appear_exactly_once_each(self):
        nodes = [node("root"), node("a", "root"), node("b", "root"), node("c", "root")]

        found = descendant_ids("root", nodes)

        self.assertEqual(found, {"a", "b", "c"})
        self.assertEqual(len(found), 3)

    def test_deep_chain_is_not_truncated(self):
        nodes = [node("n0")]
        for index in range(1, 60):
            nodes.append(node("n%d" % index, "n%d" % (index - 1)))

        found = descendant_ids("n0", nodes)

        self.assertEqual(len(found), 59)
        self.assertIn("n59", found)

    def test_cycle_terminates_instead_of_looping(self):
        # a -> c -> b -> a. The found-set guard must stop the walk.
        nodes = [node("a", "c"), node("b", "a"), node("c", "b")]

        found = descendant_ids("a", nodes)

        # The cycle makes "a" its own descendant, so it is included. That is the
        # pre-existing behaviour of both original copies, preserved here.
        self.assertEqual(found, {"a", "b", "c"})

    def test_self_parenting_node_terminates(self):
        nodes = [node("root"), node("loop", "loop")]

        # "loop" is its own parent, so it is not a child of "root"...
        self.assertEqual(descendant_ids("root", nodes), set())
        # ...and walking from it returns it once instead of spinning.
        self.assertEqual(descendant_ids("loop", nodes), {"loop"})

    def test_node_with_absent_parent_is_unreachable_from_root(self):
        # "orphan" claims a parent that is not present in the scene.
        nodes = [node("root"), node("orphan", "ghost")]

        self.assertEqual(descendant_ids("root", nodes), set())

    def test_subtree_below_an_absent_parent_is_still_walked(self):
        nodes = [node("child", "ghost"), node("grand", "child")]

        self.assertEqual(descendant_ids("child", nodes), {"grand"})

    def test_node_without_a_parent_id_is_not_treated_as_a_child(self):
        nodes = [node("root"), node("standalone")]

        self.assertEqual(descendant_ids("root", nodes), set())

    def test_empty_scene_returns_empty(self):
        self.assertEqual(descendant_ids("root", []), set())


class HasGroupAncestorTests(unittest.TestCase):
    def test_direct_child_of_group_head_has_a_group_ancestor(self):
        nodes = [node("grp", group_head=True), node("child", "grp")]

        self.assertTrue(has_group_ancestor(nodes[1], by_id(nodes)))

    def test_deep_descendant_has_a_group_ancestor(self):
        nodes = [
            node("grp", group_head=True),
            node("a", "grp"),
            node("b", "a"),
            node("c", "b"),
        ]

        self.assertTrue(has_group_ancestor(nodes[3], by_id(nodes)))

    def test_ungrouped_node_has_no_group_ancestor(self):
        nodes = [node("a"), node("b", "a")]

        self.assertFalse(has_group_ancestor(nodes[1], by_id(nodes)))

    def test_top_level_node_has_no_group_ancestor(self):
        nodes = [node("a")]

        self.assertFalse(has_group_ancestor(nodes[0], by_id(nodes)))

    def test_group_head_is_not_its_own_group_ancestor(self):
        nodes = [node("grp", group_head=True)]

        self.assertFalse(has_group_ancestor(nodes[0], by_id(nodes)))

    def test_absent_parent_ends_the_walk_as_false(self):
        nodes = [node("child", "ghost")]

        self.assertFalse(has_group_ancestor(nodes[0], by_id(nodes)))

    def test_group_head_outside_the_parent_chain_is_false(self):
        nodes = [node("grp", group_head=True), node("child", "ghost")]

        self.assertFalse(has_group_ancestor(nodes[1], by_id(nodes)))

    def test_cycle_without_a_group_head_terminates_as_false(self):
        nodes = [node("a", "b"), node("b", "a")]

        self.assertFalse(has_group_ancestor(nodes[0], by_id(nodes)))

    def test_cycle_containing_a_group_head_is_detected(self):
        nodes = [node("a", "b"), node("b", "a", group_head=True)]

        self.assertTrue(has_group_ancestor(nodes[0], by_id(nodes)))


class IsGeometryTests(unittest.TestCase):
    def test_geometryclass_superclass_is_geometry(self):
        self.assertTrue(is_geometry(node("a")))

    def test_superclass_match_ignores_case(self):
        self.assertTrue(is_geometry(node("a", superclass="geometryclass")))
        self.assertTrue(is_geometry(node("a", superclass="GEOMETRYCLASS")))

    def test_group_head_is_never_geometry(self):
        self.assertFalse(is_geometry(node("grp", group_head=True)))

    def test_other_superclasses_are_not_geometry(self):
        self.assertFalse(is_geometry(node("s", superclass="Shape")))
        self.assertFalse(is_geometry(node("h", superclass="Helper")))

    def test_match_is_a_substring_not_an_equality_check(self):
        self.assertTrue(is_geometry(node("a", superclass="SomeGeometryClassThing")))


if __name__ == "__main__":
    unittest.main()
