# Alpha/Opacity Cleanup Protection

## Purpose

Add a conservative cleanup safeguard for geometry whose assigned material depends on alpha/opacity behavior.

The goal is to prevent **Join Mesh by Material** from changing the appearance of masked/cutout assets such as foliage, decals, fences, cards, or similar geometry.

This is a cleanup safeguard, not a material conversion feature.

## Current cleanup behavior

The cleanup flow currently:

1. snapshots the scene;
2. builds a root-scoped cleanup plan;
3. classifies shape-like geometry;
4. analyzes duplicate materials;
5. asks for cleanup confirmation;
6. stages each geometry node through `_pieces_from_node()`;
7. splits Multi/Sub faces into material pieces when necessary;
8. buckets pieces by material;
9. joins each bucket;
10. deletes processed originals inside one undoable operation.

The existing adapter already contains recursive material/sub-material/sub-texture inspection for material comparison.

## Proposed behavior

Before destructive material/geometry processing, BlendMax performs an alpha/opacity preflight over the geometry in the cleanup plan.

If no affected geometry is found, cleanup proceeds unchanged.

If affected geometry is found, BlendMax shows one consolidated warning explaining that alpha/opacity controls which parts of a mesh are visible and that joining may alter its appearance.

The user chooses one of three actions:

### Skip Materials

Protect the entire affected source geometry node and its assigned material graph from Join Mesh by Material.

The protected node:

- is not passed to `_pieces_from_node()`;
- is not staged;
- is not split;
- is not bucketed;
- is not joined;
- is not added to `processed_originals`;
- is therefore not deleted by the join cleanup.

Normal cleanup continues for all non-protected geometry.

### Merge Anyway

Do not add protection. The affected geometry follows the existing cleanup path.

This is an explicit user override acknowledging that its alpha/opacity appearance may change.

### Cancel Export

Abort the cleanup/export flow before destructive execution.

No call to `execute()` should occur after cancellation.

## Multi/Sub-Object rule

We deliberately use **whole-node protection**.

If a geometry node has an assigned Multi/Sub material and any nested part of that material graph uses alpha/opacity, the whole source geometry node is protected when Skip is chosen.

Example:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

Skip protects `Tree_01` as a whole.

We do **not**:

- inspect individual faces to find only the alpha faces;
- split the source node to preserve Bark01 while joining Leaves01;
- modify the existing Multi/Sub face-splitting implementation.

This is intentional. It keeps the feature conservative and avoids introducing topology-dependent behavior into cleanup.

## Detection strategy

Detection should inspect actual material/map graph state rather than material names.

The first implementation should concentrate on texture/shader-driven opacity/alpha paths, especially:

- V-Ray material opacity map usage;
- Standard material opacity map usage where applicable;
- nested opacity/alpha-related texture connections;
- nested Multi/Sub material graphs.

Material names such as `Leaves` or `Glass` are not sufficient evidence by themselves.

Likewise, generic refraction alone should not automatically classify a material as an alpha/opacity cleanup case.

## Implementation boundary

### `blendmax_max/cleanup.py`

Keep the structural cleanup planner pure. Do not add 3ds Max material inspection here.

The existing `CleanupPlan` remains the scene-structure plan.

### `blendmax_max/max_cleanup_adapter.py`

Add the Max-side, non-mutating alpha/opacity analysis and return protected geometry/material information.

The adapter already owns material discovery and recursive material/sub-texture inspection, so this is the correct place for the detector.

### `blendmax_max/cleanup_entrypoint.py`

Insert the alpha/opacity decision after shape classification and before destructive execution.

The sequence should remain explicit and easy to follow:

```text
snapshot
→ build cleanup plan
→ classify shape-like geometry
→ shape confirmation
→ alpha/opacity analysis
→ alpha/opacity decision
→ duplicate material analysis / confirmations
→ overall cleanup confirmation
→ execute
```

### `MaxCleanupAdapter.execute()`

Accept the protected geometry IDs as an explicit execution input.

The central safety check should happen before `_pieces_from_node()`:

```python
for node_id in plan.visible_geometry_ids:
    if node_id in protected_geometry_ids:
        continue

    source = self._nodes_by_id[node_id]
    pieces = self._pieces_from_node(...)
```

This is the key invariant: **a skipped node never enters the existing Multi/Sub splitting and join path.**

## Why this is safe for the current implementation

The current execution path only deletes originals that were processed and recorded in `processed_originals`.

Therefore a skipped node that never enters `_pieces_from_node()` will also never be recorded as processed and will remain in the scene.

The existing Multi/Sub splitting code remains untouched.

The existing undo wrapper also remains the safety boundary for operations that do execute.

## Interaction with duplicate-material merging

When Skip is chosen, protected geometry and its assigned material graph must not participate in destructive material merging for that cleanup operation.

No attempt should be made in this PR to globally deduplicate or rename the resulting materials.

If Blender later shows names such as:

```text
Bark01
Bark01.001
Bark01.002
```

that is a separate cleanup/import problem and should be handled by a future PR.

## User-facing warning

Suggested copy:

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

The exact dialog API can follow the existing `queryBox()` pattern used by the cleanup adapter.

## Summary reporting

The cleanup completion summary should report how many geometry nodes were kept separate because of alpha/opacity protection.

Example:

```text
Alpha/Opacity materials protected: 3
Geometry kept separate: 4
```

The summary should describe what actually happened rather than only what was detected.

## Out of scope

This PR should not include:

- face-level alpha isolation;
- geometry splitting specifically for alpha preservation;
- Blender-side `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion or rebuilding;
- V-Ray material conversion changes;
- changes to Shapes Purge behavior.

## Validation targets

Minimum test coverage should include:

1. Opaque material only — existing cleanup behavior is unchanged.
2. Single V-Ray material with opacity map — Skip keeps the entire geometry separate.
3. Single V-Ray material with opacity map — Merge Anyway follows the existing join path.
4. Alpha/opacity detection — Cancel prevents execution/export.
5. Multi/Sub where one nested material contains opacity — Skip keeps the whole geometry node separate.
6. Multiple alpha/opacity nodes — one consolidated warning, not one dialog per object/material.
7. Mixed scene — protected geometry remains separate while normal geometry still joins.
8. Existing Shapes Purge behavior remains unchanged.
9. Cleanup remains undoable for the operations that are executed.

## Reviewer focus

The primary invariant for review is:

> **Skip means the affected source geometry node never enters Join Mesh by Material.**

The implementation should stay conservative and avoid modifying the existing Multi/Sub face-splitting logic.
