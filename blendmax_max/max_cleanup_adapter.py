"""3ds Max implementation of the explicit Join Mesh by Material cleanup."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .cleanup import (
    ROOT_GROUP_NOT_DETECTED_MESSAGE,
    CleanupPlan,
    format_face_bitarray,
    material_id_lookup,
)
from .errors import CleanupError
from .max_adapter import VRAY_MTL_PROPERTIES, MaxRuntimeAdapter


@dataclass
class _MaterialBucket:
    key: str
    material: Any
    label: str
    pieces: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialMergeCandidate:
    """One structurally identical same-name material set eligible for merging."""

    display_name: str
    merged_name: str
    fingerprint: str
    materials: Tuple[Any, ...]


@dataclass(frozen=True)
class DuplicateMaterialAnalysis:
    """Non-mutating duplicate-name analysis prepared before cleanup confirmation."""

    candidates: Tuple[MaterialMergeCandidate, ...]
    differing_name_groups: Tuple[Tuple[str, int, int], ...]


class MaxCleanupAdapter(MaxRuntimeAdapter):
    """Keep destructive Max operations behind one small runtime boundary."""

    def __init__(self, runtime=None) -> None:
        super().__init__(runtime=runtime)
        self.requires_undo = False

    def selected_root_id(self) -> str:
        selected = list(self.rt.selection)
        if len(selected) != 1:
            raise CleanupError(ROOT_GROUP_NOT_DETECTED_MESSAGE)
        root = selected[0]
        try:
            is_group_head = bool(self.rt.isGroupHead(root))
            is_open_group = bool(self.rt.isOpenGroupHead(root))
        except Exception:
            is_group_head = False
            is_open_group = False
        if not is_group_head or not is_open_group:
            raise CleanupError(ROOT_GROUP_NOT_DETECTED_MESSAGE)
        return self._anim_id(root)

    def classify_shape_like_geometry(self, plan: CleanupPlan) -> CleanupPlan:
        """Treat zero-face geometry as disposable imported linework."""

        polygon_geometry_ids = []
        shape_ids = list(plan.shape_ids)
        for node_id in plan.visible_geometry_ids:
            node = self._nodes_by_id[node_id]
            mesh = None
            try:
                mesh = self.rt.snapshotAsMesh(node)
                face_count = int(mesh.numfaces)
            except Exception:
                # If Max cannot evaluate a geometry node here, keep it in the
                # normal path so cleanup produces the more specific host error.
                polygon_geometry_ids.append(node_id)
                continue
            finally:
                if mesh is not None:
                    try:
                        self.rt.delete(mesh)
                    except Exception:
                        pass

            if face_count <= 0:
                shape_ids.append(node_id)
            else:
                polygon_geometry_ids.append(node_id)

        if not polygon_geometry_ids:
            raise CleanupError(
                "The selected Root Group contains no polygon geometry to clean."
            )
        return replace(
            plan,
            visible_geometry_ids=tuple(polygon_geometry_ids),
            shape_ids=tuple(dict.fromkeys(shape_ids)),
        )

    def confirm(self, plan: CleanupPlan) -> bool:
        return self.confirm_with_materials(plan)

    def confirm_with_materials(
        self,
        plan: CleanupPlan,
        material_merges: Sequence[MaterialMergeCandidate] = (),
        differing_name_groups: Sequence[Tuple[str, int, int]] = (),
    ) -> bool:
        root_name = str(getattr(self._nodes_by_id[plan.root_id], "name", "Unnamed"))
        merge_text = ""
        if material_merges:
            merge_text = "\nIdentical material sets to merge: {0}".format(
                len(material_merges)
            )
        differing_text = ""
        if differing_name_groups:
            differing_text = (
                "\nDuplicate-name groups with different setups kept separate: {0}"
            ).format(len(differing_name_groups))
        message = (
            "Join all meshes in the selected root by their actual material?\n\n"
            "Root group: {root}\n"
            "Input meshes: {visible}\n\n"
            "Shape objects to delete: {shapes}\n\n"
            "{merge_text}"
            "{differing_text}\n\n"
            "All nested groups will be removed.\n\n"
            "This is one undoable operation."
        ).format(
            root=root_name,
            visible=len(plan.visible_geometry_ids),
            shapes=len(plan.shape_ids),
            merge_text=merge_text,
            differing_text=differing_text,
        )
        try:
            return bool(
                self.rt.queryBox(
                    message,
                    title="BlendMax: Join Mesh by Material",
                )
            )
        except Exception:
            return False

    def confirm_material_merge(self, candidate: MaterialMergeCandidate) -> bool:
        message = (
            "{count} separate materials named \"{name}\" use the same material "
            "setup.\n\nMerge them into \"{merged}\"?\n\n"
            "All matching faces will use one copied material and become one "
            "material mesh."
        ).format(
            count=len(candidate.materials),
            name=candidate.display_name,
            merged=candidate.merged_name,
        )
        try:
            return bool(
                self.rt.queryBox(
                    message,
                    title="BlendMax: Identical Materials Detected",
                )
            )
        except Exception:
            return False

    def confirm_shape_deletion(self, plan: CleanupPlan) -> bool:
        message = (
            "This Root Group contains {count} Spline/Segment as Shapes, "
            "Delete them?"
        ).format(count=len(plan.shape_ids))
        try:
            return bool(
                self.rt.queryBox(
                    message,
                    title="BlendMax: Shape Objects Detected",
                )
            )
        except Exception:
            return False

    def _is_undefined(self, value) -> bool:
        if value is None:
            return True
        try:
            return bool(value == self.rt.undefined)
        except Exception:
            return False

    def _is_valid_node(self, node) -> bool:
        try:
            return bool(self.rt.isValidNode(node))
        except Exception:
            return node is not None

    def _set_plain_material(self, node, material) -> None:
        node.material = self.rt.undefined if material is None else material

    def _material_slots(self, material) -> Optional[Dict[int, Any]]:
        if self._is_undefined(material):
            return None
        try:
            material_ids = [int(value) for value in list(material.materialIDList)]
            materials = list(material.materialList)
        except Exception:
            return None
        if not material_ids or not materials:
            return None
        return material_id_lookup(material_ids, materials)

    @staticmethod
    def _normalized_material_name(material) -> str:
        value = str(getattr(material, "name", "Material")).strip() or "Material"
        return " ".join(value.split()).casefold()

    def _comparison_properties(
        self,
        animatable,
        class_name: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """Capture deterministic public values for equality, not conversion."""

        try:
            property_names = list(self.rt.getPropNames(animatable))
        except Exception:
            return {}, False

        values: Dict[str, Any] = {}
        reliable = True
        for property_name in property_names:
            key = str(property_name)
            lowered = key.casefold()
            if lowered == "name":
                continue
            if class_name.casefold() == "vraymtl" and not (
                lowered in VRAY_MTL_PROPERTIES or lowered.startswith("texmap_")
            ):
                continue
            try:
                value = self.rt.getProperty(animatable, property_name)
            except Exception:
                reliable = False
                continue

            supported, encoded = self._primitive_value(value)
            if supported:
                values[lowered] = encoded
                continue

            # Materials and maps are represented through their explicit slot
            # topology below. Other public value types retain their class and
            # display value so a detectable difference prevents a merge.
            try:
                superclass = self._superclass_name(value).casefold()
            except Exception:
                superclass = "unknown"
            if "material" in superclass or "texture" in superclass or "texmap" in superclass:
                continue
            try:
                display_value = str(value)
            except Exception:
                reliable = False
                continue
            values[lowered] = {
                "class": self._class_name(value).casefold(),
                "value": display_value,
            }
        return dict(sorted(values.items())), reliable

    def _comparison_graph(
        self,
        animatable,
        kind: str,
        stack: Tuple[str, ...] = (),
        depth: int = 0,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        if self._is_undefined(animatable):
            return None, True
        if depth > 32:
            return {"kind": kind, "depth_limit": True}, False

        anim_id = self._anim_id(animatable)
        class_name = self._class_name(animatable)
        if anim_id in stack:
            return {
                "kind": kind,
                "class": class_name.casefold(),
                "cycle": True,
            }, True

        parameters, reliable = self._comparison_properties(animatable, class_name)
        entry: Dict[str, Any] = {
            "kind": kind,
            "class": class_name.casefold(),
            "parameters": parameters,
            "sub_materials": [],
            "sub_textures": [],
        }
        child_stack = stack + (anim_id,)

        try:
            sub_material_count = int(self.rt.getNumSubMtls(animatable))
        except Exception:
            sub_material_count = 0
            reliable = False
        for index in range(1, sub_material_count + 1):
            try:
                child = self.rt.getSubMtl(animatable, index)
            except Exception:
                reliable = False
                continue
            try:
                slot = str(self.rt.getSubMtlSlotName(animatable, index))
            except Exception:
                slot = str(index)
            child_graph, child_reliable = self._comparison_graph(
                child,
                "material",
                child_stack,
                depth + 1,
            )
            reliable = reliable and child_reliable
            entry["sub_materials"].append(
                {"index": index, "slot": slot.casefold(), "value": child_graph}
            )

        try:
            sub_texture_count = int(self.rt.getNumSubTexmaps(animatable))
        except Exception:
            sub_texture_count = 0
            reliable = False
        for index in range(1, sub_texture_count + 1):
            try:
                child = self.rt.getSubTexmap(animatable, index)
            except Exception:
                reliable = False
                continue
            try:
                slot = str(self.rt.getSubTexmapSlotName(animatable, index))
            except Exception:
                slot = str(index)
            child_graph, child_reliable = self._comparison_graph(
                child,
                "texture",
                child_stack,
                depth + 1,
            )
            reliable = reliable and child_reliable
            entry["sub_textures"].append(
                {"index": index, "slot": slot.casefold(), "value": child_graph}
            )

        return entry, reliable

    def material_fingerprint(self, material) -> str:
        graph, reliable = self._comparison_graph(material, "material")
        if not reliable:
            # Never merge two materials whose complete public setup could not
            # be inspected. The handle deliberately makes each one distinct.
            return "unreliable:{0}".format(self._anim_id(material))
        serialized = json.dumps(
            graph,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def _cleanup_bucket_materials(self, plan: CleanupPlan) -> List[Any]:
        materials = []
        seen = set()
        for node_id in plan.visible_geometry_ids:
            node = self._nodes_by_id[node_id]
            assigned = getattr(node, "material", None)
            slots = self._material_slots(assigned)
            candidates = list(slots.values()) if slots is not None else [assigned]
            for material in candidates:
                if self._is_undefined(material):
                    continue
                material_id = self._anim_id(material)
                if material_id in seen:
                    continue
                seen.add(material_id)
                materials.append(material)
        return materials

    def analyze_duplicate_materials(
        self,
        plan: CleanupPlan,
    ) -> DuplicateMaterialAnalysis:
        by_name: Dict[str, List[Any]] = {}
        display_names: Dict[str, str] = {}
        for material in self._cleanup_bucket_materials(plan):
            normalized = self._normalized_material_name(material)
            by_name.setdefault(normalized, []).append(material)
            display_names.setdefault(
                normalized,
                str(getattr(material, "name", "Material")).strip() or "Material",
            )

        candidates: List[MaterialMergeCandidate] = []
        differing: List[Tuple[str, int, int]] = []
        for normalized_name in sorted(by_name):
            same_name = by_name[normalized_name]
            if len(same_name) < 2:
                continue
            by_fingerprint: Dict[str, List[Any]] = {}
            for material in same_name:
                by_fingerprint.setdefault(
                    self.material_fingerprint(material),
                    [],
                ).append(material)
            if len(by_fingerprint) > 1:
                differing.append(
                    (
                        display_names[normalized_name],
                        len(same_name),
                        len(by_fingerprint),
                    )
                )

            mergeable_sets = [
                (fingerprint, materials)
                for fingerprint, materials in sorted(by_fingerprint.items())
                if len(materials) > 1 and not fingerprint.startswith("unreliable:")
            ]
            for variant_index, (fingerprint, materials) in enumerate(
                mergeable_sets,
                start=1,
            ):
                base_name = display_names[normalized_name]
                merged_name = "{0}_MERGED".format(base_name)
                if len(mergeable_sets) > 1:
                    merged_name = "{0}_{1:02d}".format(merged_name, variant_index)
                candidates.append(
                    MaterialMergeCandidate(
                        display_name=base_name,
                        merged_name=merged_name,
                        fingerprint=fingerprint,
                        materials=tuple(materials),
                    )
                )

        return DuplicateMaterialAnalysis(
            candidates=tuple(candidates),
            differing_name_groups=tuple(differing),
        )

    def _material_replacements(
        self,
        material_merges: Sequence[MaterialMergeCandidate],
    ) -> Dict[str, Any]:
        replacements: Dict[str, Any] = {}
        for candidate in material_merges:
            try:
                merged = self.rt.copy(candidate.materials[0])
                merged.name = candidate.merged_name
            except Exception as exc:
                raise CleanupError(
                    "Could not create merged material {0}: {1}".format(
                        candidate.merged_name,
                        exc,
                    )
                )
            for material in candidate.materials:
                replacements[self._anim_id(material)] = merged
        return replacements

    def _replacement_material(self, material, replacements: Dict[str, Any]):
        if self._is_undefined(material):
            return material
        return replacements.get(self._anim_id(material), material)

    def _bucket_identity(
        self,
        material,
        parent_material=None,
        face_material_id: Optional[int] = None,
    ) -> Tuple[str, Any, str]:
        if self._is_undefined(material):
            if parent_material is not None and face_material_id is not None:
                key = "unresolved:{0}:{1}".format(
                    self._anim_id(parent_material),
                    face_material_id,
                )
                return key, parent_material, "Unresolved Material ID {0}".format(
                    face_material_id
                )
            return "material:none", None, "No Material"
        label = str(getattr(material, "name", "Material")) or "Material"
        return "material:{0}".format(self._anim_id(material)), material, label

    def _detach_from_parent(self, node) -> None:
        transform = node.transform
        try:
            if bool(self.rt.isGroupMember(node)):
                self.rt.setGroupMember(node, False)
        except Exception:
            pass
        try:
            node.parent = self.rt.undefined
        except Exception:
            pass
        node.transform = transform

    def _copy_as_editable_poly(self, source, created_nodes: List[Any]):
        try:
            staging = self.rt.copy(source)
        except Exception as exc:
            raise CleanupError(
                "Could not stage a copy of {0}: {1}".format(source.name, exc)
            )
        created_nodes.append(staging)
        staging.name = str(self.rt.uniqueName("BM_Stage_"))
        self._detach_from_parent(staging)
        try:
            self.rt.convertToPoly(staging)
        except Exception as exc:
            raise CleanupError(
                "Could not convert {0} to Editable Poly: {1}".format(
                    source.name,
                    exc,
                )
            )
        return staging

    def _bitarray(self, face_indices: Iterable[int]):
        return self.rt.execute(format_face_bitarray(face_indices))

    def _face_sets_by_material_id(self, node) -> List[Tuple[int, Any]]:
        """Collect face BitArrays in one Max-side pass, with a safe fallback."""

        try:
            handle = int(self.rt.getHandleByAnim(node))
            script = """
            (
                local bmNode = maxOps.getNodeByHandle {handle}
                if bmNode == undefined then throw "BlendMax staging node is missing"
                local bmIds = #()
                local bmSets = #()
                local bmFaceCount = polyop.getNumFaces bmNode
                for bmFace = 1 to bmFaceCount do
                (
                    local bmId = polyop.getFaceMatID bmNode bmFace
                    local bmIndex = findItem bmIds bmId
                    if bmIndex == 0 do
                    (
                        append bmIds bmId
                        append bmSets #{{}}
                        bmIndex = bmIds.count
                    )
                    bmSets[bmIndex][bmFace] = true
                )
                #(bmIds, bmSets)
            )
            """.format(handle=handle)
            result = self.rt.execute(script)
            material_ids = [int(value) for value in list(result[0])]
            face_sets = list(result[1])
            if len(material_ids) != len(face_sets):
                raise ValueError("Max returned mismatched face material sets")
            return list(zip(material_ids, face_sets))
        except Exception:
            # Keep a straightforward pymxs fallback for hosts that reject the
            # optimized expression. Only the visible staging copy is inspected.
            face_count = int(self.rt.polyop.getNumFaces(node))
            indices_by_id: Dict[int, List[int]] = {}
            for face_index in range(1, face_count + 1):
                material_id = int(self.rt.polyop.getFaceMatID(node, face_index))
                indices_by_id.setdefault(material_id, []).append(face_index)
            return [
                (material_id, self._bitarray(face_indices))
                for material_id, face_indices in indices_by_id.items()
            ]

    def _normalize_face_material_ids(self, node) -> None:
        try:
            face_count = int(self.rt.polyop.getNumFaces(node))
            if face_count > 0:
                self.rt.polyop.setFaceMatID(
                    node,
                    self._bitarray(range(1, face_count + 1)),
                    1,
                )
        except Exception:
            # A plain material does not depend on the stored per-face IDs.
            pass

    def _find_node_by_name(self, name: str):
        try:
            return self.rt.getNodeByName(name, exact=True)
        except Exception:
            for node in list(self.rt.objects):
                if str(getattr(node, "name", "")) == name:
                    return node
        return None

    def _detach_piece(
        self,
        staging,
        face_selection,
        created_nodes: List[Any],
    ):
        piece_name = "BM_Piece_{0}".format(uuid.uuid4().hex)
        try:
            result = self.rt.polyop.detachFaces(
                staging,
                face_selection,
                delete=False,
                asNode=True,
                name=piece_name,
            )
        except Exception as exc:
            raise CleanupError("Could not split material faces: {0}".format(exc))
        if result is False:
            raise CleanupError("3ds Max refused to split a material face set.")
        piece = self._find_node_by_name(piece_name)
        if piece is None:
            raise CleanupError("3ds Max did not return the detached material mesh.")
        created_nodes.append(piece)
        self._detach_from_parent(piece)
        return piece

    def _pieces_from_node(
        self,
        source,
        created_nodes: List[Any],
        warnings: List[str],
        material_replacements: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, Any, str, Any]]:
        replacements = material_replacements or {}
        staging = self._copy_as_editable_poly(source, created_nodes)
        try:
            face_count = int(self.rt.polyop.getNumFaces(staging))
        except Exception as exc:
            raise CleanupError(
                "Could not inspect faces on {0}: {1}".format(source.name, exc)
            )
        if face_count <= 0:
            warnings.append("Skipped empty mesh: {0}".format(source.name))
            self.rt.delete(staging)
            return []

        parent_material = getattr(source, "material", None)
        slots = self._material_slots(parent_material)
        if slots is None:
            output_material = self._replacement_material(
                parent_material,
                replacements,
            )
            key, material, label = self._bucket_identity(output_material)
            self._set_plain_material(staging, material)
            self._normalize_face_material_ids(staging)
            return [(key, material, label, staging)]

        face_sets: Dict[str, Dict[str, Any]] = {}
        unresolved_ids = set()
        try:
            material_face_sets = self._face_sets_by_material_id(staging)
        except Exception as exc:
            raise CleanupError(
                "Could not read face material IDs on {0}: {1}".format(
                    source.name,
                    exc,
                )
            )
        for face_material_id, face_selection in material_face_sets:
            if face_material_id in slots:
                leaf_material = slots[face_material_id]
                if self._is_undefined(leaf_material):
                    key, material, label = self._bucket_identity(None)
                else:
                    output_material = self._replacement_material(
                        leaf_material,
                        replacements,
                    )
                    key, material, label = self._bucket_identity(output_material)
            else:
                unresolved_ids.add(face_material_id)
                key, material, label = self._bucket_identity(
                    None,
                    parent_material=parent_material,
                    face_material_id=face_material_id,
                )
            entry = face_sets.setdefault(
                key,
                {
                    "material": material,
                    "label": label,
                    "face_sets": [],
                },
            )
            entry["face_sets"].append(face_selection)

        if unresolved_ids:
            warnings.append(
                "{0} uses unresolved Multi/Sub material ID(s): {1}".format(
                    source.name,
                    ", ".join(str(value) for value in sorted(unresolved_ids)),
                )
            )

        if len(face_sets) == 1:
            key, entry = next(iter(face_sets.items()))
            self._set_plain_material(staging, entry["material"])
            self._normalize_face_material_ids(staging)
            return [(key, entry["material"], entry["label"], staging)]

        pieces = []
        for key, entry in face_sets.items():
            for face_selection in entry["face_sets"]:
                piece = self._detach_piece(staging, face_selection, created_nodes)
                self._set_plain_material(piece, entry["material"])
                self._normalize_face_material_ids(piece)
                pieces.append((key, entry["material"], entry["label"], piece))
        self.rt.delete(staging)
        return pieces

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(value)).strip(" ._")
        return cleaned[:72] or "Material"

    def _join_bucket(self, bucket: _MaterialBucket):
        target = bucket.pieces[0]
        self._set_plain_material(target, bucket.material)
        for source in bucket.pieces[1:]:
            try:
                result = self.rt.polyop.attach(target, source)
            except Exception as exc:
                raise CleanupError(
                    "Could not join material {0}: {1}".format(bucket.label, exc)
                )
            if result is False:
                raise CleanupError(
                    "3ds Max refused to join material {0}.".format(bucket.label)
                )
        self._set_plain_material(target, bucket.material)
        self._normalize_face_material_ids(target)
        target.name = str(
            self.rt.uniqueName("BM_{0}_".format(self._safe_name(bucket.label)))
        )
        return target

    def _node_depth(self, node_id: str) -> int:
        depth = 0
        current = self._nodes_by_id.get(node_id)
        visited = set()
        while current is not None:
            current_id = self._anim_id(current)
            if current_id in visited:
                break
            visited.add(current_id)
            parent = getattr(current, "parent", None)
            if parent is None or self._is_undefined(parent):
                break
            depth += 1
            current = parent
        return depth

    def _remove_nested_groups(
        self,
        plan: CleanupPlan,
        warnings: List[str],
    ) -> int:
        removed = 0
        ordered = sorted(
            plan.removable_group_ids,
            key=self._node_depth,
            reverse=True,
        )
        for node_id in ordered:
            group_head = self._nodes_by_id.get(node_id)
            if group_head is None or not self._is_valid_node(group_head):
                continue
            try:
                self.rt.ungroup(group_head)
                removed += 1
            except Exception as exc:
                warnings.append(
                    "Could not remove nested group {0}: {1}".format(
                        getattr(group_head, "name", node_id),
                        exc,
                    )
                )
        return removed

    def _delete_created(self, created_nodes: Iterable[Any]) -> None:
        for node in reversed(list(created_nodes)):
            if not self._is_valid_node(node):
                continue
            try:
                self.rt.delete(node)
            except Exception:
                pass

    def execute(
        self,
        plan: CleanupPlan,
        material_merges: Sequence[MaterialMergeCandidate] = (),
    ) -> Dict[str, Any]:
        self.requires_undo = False
        root = self._nodes_by_id[plan.root_id]
        shape_nodes = [self._nodes_by_id[node_id] for node_id in plan.shape_ids]
        created_nodes: List[Any] = []
        processed_originals: List[Any] = []
        warnings: List[str] = []
        destructive_started = False
        root_was_open = False
        root_state_known = False

        try:
            material_replacements = self._material_replacements(material_merges)
            buckets: Dict[str, _MaterialBucket] = {}
            for node_id in plan.visible_geometry_ids:
                source = self._nodes_by_id[node_id]
                pieces = self._pieces_from_node(
                    source,
                    created_nodes,
                    warnings,
                    material_replacements,
                )
                if not pieces:
                    continue
                processed_originals.append(source)
                for key, material, label, piece in pieces:
                    bucket = buckets.setdefault(
                        key,
                        _MaterialBucket(key=key, material=material, label=label),
                    )
                    bucket.pieces.append(piece)

            if not buckets:
                raise CleanupError("No material-bearing mesh faces were available to join.")

            outputs = [self._join_bucket(bucket) for bucket in buckets.values()]

            try:
                root_was_open = bool(self.rt.isOpenGroupHead(root))
                root_state_known = True
                if not root_was_open:
                    self.rt.setGroupOpen(root, True)
            except Exception as exc:
                raise CleanupError("Could not open the selected root group: {0}".format(exc))

            try:
                self.rt.attachNodesToGroup(self.rt.Array(*outputs), root)
            except Exception as exc:
                raise CleanupError(
                    "Could not attach cleaned meshes to the root group: {0}".format(exc)
                )

            destructive_started = True
            self.requires_undo = True
            for source in processed_originals:
                self.rt.delete(source)
            for shape in shape_nodes:
                self.rt.delete(shape)

            removed_group_count = self._remove_nested_groups(plan, warnings)
            self.rt.clearSelection()
            self.rt.select(root)
            self.requires_undo = False
            return {
                "input_mesh_count": len(processed_originals),
                "output_mesh_count": len(outputs),
                "deleted_shape_count": len(shape_nodes),
                "removed_group_count": removed_group_count,
                "merged_material_set_count": len(material_merges),
                "replaced_material_count": sum(
                    len(candidate.materials) for candidate in material_merges
                ),
                "warnings": warnings,
            }
        except CleanupError:
            if not destructive_started:
                self._delete_created(created_nodes)
            raise
        except Exception as exc:
            if not destructive_started:
                self._delete_created(created_nodes)
            raise CleanupError("Join Mesh by Material failed: {0}".format(exc))
        finally:
            if root_state_known and self._is_valid_node(root):
                try:
                    current_open = bool(self.rt.isOpenGroupHead(root))
                    if current_open != root_was_open:
                        self.rt.setGroupOpen(root, root_was_open)
                except Exception:
                    pass
