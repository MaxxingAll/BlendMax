# Alpha/Opacity Cleanup Protection — Reviewer Proposal

This file records the proposed implementation before touching the destructive cleanup code.

## Goal

Protect geometry whose assigned material relies on alpha/opacity behavior from **Join Mesh by Material** when the user chooses to skip it.

## Current code path

`cleanup_entrypoint.py` currently builds the cleanup plan, classifies shape-like geometry, confirms shape deletion, analyzes duplicate materials, confirms material merges, confirms the overall cleanup, and only then calls `MaxCleanupAdapter.execute()` inside one undoable operation.

`MaxCleanupAdapter.execute()` currently sends every `plan.visible_geometry_ids` node through `_pieces_from_node()`. `_pieces_from_node()` can convert a node to Editable Poly, inspect Multi/Sub face material IDs, detach per-material face sets, bucket them, and finally join buckets. Processed originals are then deleted.

## Proposed change

Add a non-mutating alpha/opacity preflight before destructive execution.

For each geometry node in the cleanup plan:

```text
geometry node
    ↓
assigned material
    ↓
inspect actual material/map graph
    ↓
alpha/opacity usage found?
```

Do not use material names as detection evidence.

When alpha/opacity usage is found, collect the affected geometry nodes and show one consolidated warning.

## User choices

### Skip Materials

Protect the **whole geometry node** and its assigned material graph for this cleanup operation.

The protected geometry must not enter `_pieces_from_node()`, so it is never staged, split, bucketed, joined, or recorded in `processed_originals`.

Normal cleanup continues for all other geometry.

### Merge Anyway

No protection is applied. The existing cleanup path is allowed to process the affected geometry.

### Cancel Export

Abort before `execute()` is called. No destructive cleanup/export operation should start after cancellation.

## Multi/Sub policy

If the assigned material is a Multi/Sub-Object material and **any nested material/texture path uses alpha/opacity**, protect the entire geometry node when Skip is selected.

Example:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

`Tree_01` remains completely separate.

Do not inspect individual faces and do not modify the existing Multi/Sub detachment logic.

This intentionally favors visual safety over maximum joining efficiency.

## Detection notes

3ds Max exposes opacity/opacity-map state on Standard material types and map slots separately. V-Ray documents opacity-map usage for foliage cutouts, including leaf workflows. Therefore detection should inspect actual material/map state rather than relying on names such as `Leaves` or `Alpha`.

The repository already contains recursive material/sub-material/sub-texture traversal in `MaxCleanupAdapter` for material fingerprinting. Reuse the same traversal pattern for a focused alpha/opacity detector.

Do not classify every refractive material as an alpha/opacity case. The first implementation should target texture/shader-driven opacity/alpha behavior relevant to cutout transparency.

## Recommended implementation boundary

### `blendmax_max/max_cleanup_adapter.py`

Add:

- alpha/opacity detector;
- non-mutating geometry/material analysis;
- consolidated alpha warning dialog;
- protected geometry/material IDs returned to the entrypoint.

### `blendmax_max/cleanup_entrypoint.py`

Insert the alpha/opacity decision before destructive execution.

Conceptually:

```text
snapshot
→ build cleanup plan
→ classify shapes
→ shape confirmation
→ alpha/opacity analysis
→ alpha/opacity decision
→ duplicate material analysis
→ overall cleanup confirmation
→ execute
```

### `MaxCleanupAdapter.execute()`

Add an explicit protected-geometry input and filter it before `_pieces_from_node()`:

```python
for node_id in plan.visible_geometry_ids:
    if node_id in protected_geometry_ids:
        continue
    # existing processing
```

This is the critical safety boundary.

## Data design

Keep `CleanupPlan` focused on structural scene planning. Do not make `cleanup.py` depend on Max material inspection.

Pass protected geometry IDs explicitly into execution rather than treating protection as part of the immutable scene plan.

A small analysis result such as the following is sufficient:

```python
@dataclass(frozen=True)
class AlphaOpacityAnalysis:
    protected_geometry_ids: Tuple[str, ...]
    protected_material_ids: Tuple[str, ...]
```

The protected material IDs are useful to prevent the same assigned material from entering destructive material merge logic during this cleanup operation.

## Summary

Add actual-result reporting, for example:

```text
Alpha/Opacity materials protected: 3
Geometry kept separate: 4
```

## Out of scope

- Face-level alpha isolation.
- Splitting a Multi/Sub node specifically to preserve only alpha faces.
- Blender-side `.001` material deduplication.
- Material rename cleanup.
- Alpha shader conversion/rebuilding.
- V-Ray material conversion changes.
- Changes to Shapes Purge.

## Validation

At minimum test:

1. Opaque-only scene: unchanged behavior.
2. V-Ray material with opacity map + Skip: geometry stays separate.
3. Same case + Merge Anyway: existing join path is used.
4. Alpha/opacity case + Cancel: `execute()` is never reached.
5. Multi/Sub with one nested alpha material + Skip: whole node stays separate.
6. Multiple affected nodes: one consolidated warning.
7. Mixed scene: protected nodes stay separate while normal nodes join.
8. Shapes Purge behavior is unchanged.
9. Executed cleanup remains undoable.

## Reviewer focus

The key invariant is:

> **Skip means the affected source geometry node never enters Join Mesh by Material.**

This PR should remain conservative and should not change the existing Multi/Sub face-splitting implementation.
