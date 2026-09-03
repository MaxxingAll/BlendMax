# Alpha / Opacity Cleanup Protection

Implementation specification for protecting whole geometry nodes whose assigned material graph uses alpha/opacity behavior during Join Mesh by Material cleanup.

## Facts from the current code

- `cleanup.py` owns the structural `CleanupPlan` and has no 3ds Max material dependency.
- `cleanup_entrypoint.py` controls the interactive sequence and only starts destructive work when it calls `execute()` inside the undoable block.
- `MaxCleanupAdapter` owns material inspection, duplicate-material analysis, Multi/Sub handling, and join execution.
- `_pieces_from_node()` is the destructive staging/Multi/Sub splitting boundary.
- `execute()` deletes only originals recorded in `processed_originals`.

Therefore the protection boundary is **before `_pieces_from_node()`**.

## Detection rules

Detect from actual material/map state; material names are never sufficient.

### Standard Material

Trigger protection for a geometry assignment when:

- `opacityMap` is enabled by `opacityMapEnable`; or
- constant `opacity` is below 100.

An opacity map that exists but is disabled does not trigger protection by itself. A reduced constant opacity still affects appearance and triggers protection.

### VRayMtl

Trigger protection when the V-Ray material exposes an enabled opacity texture connection, including:

- `texmap_opacity`
- `texmap_opacity_on`

A present-but-disabled opacity texture does not trigger protection by itself. Any exposed non-default constant opacity state that changes appearance should still trigger protection.

Do not classify refraction alone as alpha/opacity protection.

### Recursive material graph / Multi/Sub

Reuse the existing recursive material/sub-material/sub-texture traversal model. If any nested path contains qualifying alpha/opacity usage, protect the **entire source geometry node** using the assigned material graph.

Example:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

Selecting **Skip Materials** protects the entire `Tree_01` node and leaves its full assigned Multi/Sub graph out of destructive cleanup. We do not inspect faces or split the node to save Bark01.

## User interaction

Run one consolidated warning after alpha/opacity preflight and before destructive execution:

```text
⚠ Alpha / Opacity Materials Detected

BlendMax found materials using alpha/opacity maps or settings.
These materials can control which parts of a mesh are visible.
Joining or simplifying them may change their appearance.

Affected geometry:
  • Tree_01
  • Grass_01
  • Fence_01

How would you like to proceed?

[ Skip Materials ] [ Merge Anyway ] [ Cancel Export ]
```

### Skip Materials

Protect affected geometry for this cleanup operation. Protected nodes:

- never enter `_pieces_from_node()`;
- are not staged, split, bucketed, or joined;
- are not recorded in `processed_originals`;
- remain in the scene.

### Merge Anyway

No protection set is populated. Existing cleanup behavior remains available.

### Cancel Export

Abort before `execute()` starts. No destructive cleanup/export mutation occurs.

## Three-way UI implementation

Current confirmations use boolean-only `rt.queryBox()`. It cannot represent three distinct outcomes safely.

Preferred implementation: a small Max-side modal rollout/dialog with explicit **Skip Materials**, **Merge Anyway**, and **Cancel Export** actions returning an enum/string such as `SKIP`, `MERGE`, or `CANCEL`.

A chained query-box flow is acceptable only if Cancel remains unambiguous. Do not overload a single boolean result.

## Analysis order

```text
snapshot_scene()
  ↓
build_cleanup_plan()
  ↓
classify_shape_like_geometry()
  ↓
confirm_shape_deletion()
  ↓
analyze alpha/opacity usage
  ↓
alpha decision (skip / merge / cancel)
  ↓
analyze duplicate materials using protected geometry filter
  ↓
confirm overall cleanup
  ↓
execute()
```

## Duplicate-material analysis

`_cleanup_bucket_materials()` currently iterates all `plan.visible_geometry_ids`. Update duplicate-material analysis to exclude protected geometry before gathering materials, e.g.:

```python
analyze_duplicate_materials(
    plan,
    protected_geometry_ids=(),
)
```

The protected set must prevent skipped geometry from creating duplicate-material merge decisions.

## Execution

Pass `protected_geometry_ids` explicitly to `execute()` rather than adding Max-specific state to the pure structural `CleanupPlan`:

```python
execute(
    plan,
    material_merges=approved_material_merges,
    protected_geometry_ids=protected_geometry_ids,
)
```

Filter at the current loop over `plan.visible_geometry_ids`, before `_pieces_from_node()`:

```python
for node_id in plan.visible_geometry_ids:
    if node_id in protected_geometry_ids:
        continue
    source = self._nodes_by_id[node_id]
    pieces = self._pieces_from_node(...)
```

Do not modify the existing Multi/Sub face-detach implementation for this feature.

## All-protected case

If all source geometry is protected, the cleanup should return an informational no-op rather than raising `No material-bearing mesh faces were available to join.` Original nodes and materials remain intact.

## Completion summary

Add explicit result keys and output:

```text
Alpha/Opacity materials protected: N
Geometry kept separate: N
```

`cleanup_entrypoint.py` must format the new keys explicitly.

## Tests

At minimum:

1. Opaque Standard material → unchanged normal cleanup.
2. Standard enabled opacity map → warning/protection.
3. Standard disabled opacity map → no map-triggered protection.
4. Standard opacity below 100 → warning/protection.
5. V-Ray enabled opacity map → warning/protection.
6. V-Ray opacity map present but disabled → no map-triggered protection.
7. Multi/Sub with one nested alpha path → whole source node protected.
8. Mixed protected/joinable scene → only joinable nodes enter `_pieces_from_node()`.
9. Protected geometry is excluded from duplicate-material analysis.
10. Merge Anyway → existing cleanup path remains available.
11. Cancel Export → `execute()` is never called.
12. All-protected input → clean informational no-op.
13. Existing Shapes Purge behavior remains unchanged.
14. Executed cleanup remains undoable.

## Out of scope

- face-level alpha isolation;
- partial Multi/Sub splitting;
- Blender `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.

## Research basis

The detector follows documented 3ds Max material/map state and Chaos V-Ray opacity-map behavior. See `docs/ALPHA_OPACITY_RESEARCH_NOTES.md` for source links.
