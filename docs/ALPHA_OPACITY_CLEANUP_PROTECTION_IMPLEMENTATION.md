# Alpha/Opacity Cleanup Protection — Implementation Proposal

## Intent

Prevent Join Mesh by Material from altering geometry whose assigned material uses alpha/opacity behavior when the user chooses **Skip Materials**.

## Facts from the current BlendMax implementation

- `cleanup.py` owns the structural `CleanupPlan` and has no 3ds Max material dependency.
- `cleanup_entrypoint.py` controls the interactive cleanup sequence and starts destructive execution only inside the undoable `execute()` block.
- `MaxCleanupAdapter` owns material inspection, duplicate-material analysis, material replacement, Multi/Sub handling, and the actual join execution.
- `_pieces_from_node()` currently stages geometry, reads Multi/Sub face material IDs, detaches material face sets when needed, and creates join buckets.
- `execute()` only deletes original nodes that were processed and recorded in `processed_originals`.

These facts make the safest implementation: detect first, decide once, and prevent protected geometry from entering `_pieces_from_node()` at all.

## Detection

Implement a focused Max-side detector in `max_cleanup_adapter.py` that walks the assigned material graph and identifies texture/shader-driven alpha/opacity usage.

Detection should inspect real material/map state, not material names.

Relevant cases include:

- V-Ray material opacity map usage;
- Standard material opacity map usage where supported;
- nested texture/map connections that feed opacity/alpha behavior;
- Multi/Sub materials whose nested graph contains an alpha/opacity path.

Do not classify generic refraction by itself as an alpha/opacity hit.

The existing recursive material/sub-material/sub-texture traversal used by `material_fingerprint()` can be reused as the traversal model.

## Whole-node protection

When an assigned material graph is detected as alpha/opacity and the user chooses Skip, protect the entire source geometry node.

For Multi/Sub, do not inspect faces. If any nested material is alpha/opacity-sensitive, the whole geometry node is protected.

Example:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

Skip keeps `Tree_01` entirely separate.

## Data flow

Use a small Max-side analysis result rather than changing the pure structural planner:

```python
@dataclass(frozen=True)
class AlphaOpacityAnalysis:
    protected_geometry_ids: Tuple[str, ...]
    protected_material_ids: Tuple[str, ...]
```

`protected_geometry_ids` controls the join boundary.

`protected_material_ids` prevents the associated material graph from participating in destructive material merging for this operation.

## Entry-point behavior

The interactive flow should become:

```text
snapshot
→ build cleanup plan
→ classify shape-like geometry
→ confirm shape deletion
→ analyze alpha/opacity
→ if needed: Skip / Merge Anyway / Cancel Export
→ analyze duplicate materials
→ confirm overall cleanup
→ execute
```

The alpha dialog should be consolidated: one decision for all affected geometry in the current cleanup operation.

## User choices

### Skip Materials

Populate protection sets and continue.

Protected geometry:

- is excluded before `_pieces_from_node()`;
- is never staged;
- is never split;
- is never bucketed;
- is never joined;
- is not recorded in `processed_originals`;
- remains in the scene.

### Merge Anyway

Do not populate the protection sets. Existing cleanup behavior is used.

### Cancel Export

Return before `execute()` is reached.

## Execution change

Add protected geometry input to `MaxCleanupAdapter.execute()`.

The first loop over `plan.visible_geometry_ids` should filter protected nodes before any staging:

```python
for node_id in plan.visible_geometry_ids:
    if node_id in protected_geometry_ids:
        continue
    source = self._nodes_by_id[node_id]
    pieces = self._pieces_from_node(...)
```

Do not implement protection by joining first and trying to restore later.

## Material merge interaction

The duplicate-material analysis currently gathers materials from the cleanup bucket population. Protected geometry must not contribute to destructive material merge decisions when Skip is selected.

The simplest safe rule is to use the same protected-material set during cleanup material collection and replacement generation.

This PR does not need to solve global material deduplication after import.

## Why no `CleanupPlan` field is required

The structural plan answers: "What geometry is in the selected root?"

Alpha/opacity protection answers: "What did the user decide not to join?"

Keeping these separate avoids putting Max-runtime material knowledge into the pure planner and keeps the user decision explicit at execution time.

## UI copy

```text
⚠ Alpha / Opacity Materials Detected

BlendMax found materials that use alpha/opacity maps.
These maps control which parts of a mesh are visible, such as
leaves and other cutout surfaces.

Joining these objects may alter their appearance.

Affected geometry:
  • Tree_01
  • Grass_01
  • Fence_01

How would you like to proceed?

[ Skip Materials ] [ Merge Anyway ] [ Cancel Export ]
```

## Summary

Report actual protection results:

```text
Alpha/Opacity materials protected: 3
Geometry kept separate: 4
```

## Tests

- Opaque scene: no behavior change.
- V-Ray opacity map: Skip keeps geometry intact and separate.
- V-Ray opacity map: Merge Anyway reaches existing cleanup.
- Cancel: execute is not called.
- Multi/Sub with nested opacity: Skip protects whole source node.
- Multiple affected nodes: one consolidated dialog.
- Mixed protected/non-protected scene: normal geometry still joins.
- Shapes Purge remains unchanged.
- Cleanup remains undoable for executed changes.
