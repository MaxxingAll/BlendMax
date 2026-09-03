# Alpha/Opacity Cleanup Protection

## Status

Implemented on `feat/alpha-opacity-cleanup-protection`.

## Purpose

Prevent **Join Mesh by Material** cleanup from altering the appearance of geometry whose assigned material graph uses alpha/opacity behavior.

The implementation is intentionally conservative: when the user chooses **Skip Materials**, the entire affected source geometry node remains separate. No face-level isolation is attempted.

## Current behavior

The cleanup flow now performs alpha/opacity preflight after shape classification and before duplicate-material analysis/execution.

If no alpha/opacity geometry is found, the existing cleanup path is unchanged.

If affected geometry is found, BlendMax presents a consolidated explanation and offers:

- **Skip Materials** — exclude the entire affected geometry node from Join Mesh by Material and keep its assigned material graph out of destructive material merging for this operation.
- **Merge Anyway** — continue with the existing cleanup behavior.
- **Cancel Export** — stop before destructive execution.

## Detection rules

Detection uses actual material/map state rather than material names.

### Standard Material

A source geometry is flagged when its assigned material exposes:

- an `opacityMap` that is enabled by `opacityMapEnable`; or
- constant `opacity` below 100.

A populated but disabled opacity map does not trigger protection by itself.

### V-Ray Material

A source geometry is flagged when its V-Ray material exposes an opacity texture connection with the corresponding enable state:

- `texmap_opacity`
- `texmap_opacity_on`

A populated opacity texture whose enable state is false does not trigger protection by itself. Refraction alone is not treated as alpha/opacity protection.

### Recursive graph / Multi/Sub

Material and sub-material/sub-texture traversal is recursive. If any nested material or texture path contains qualifying alpha/opacity behavior, the assigned source geometry node is flagged.

For a Multi/Sub material, the rule is deliberately whole-node:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

With **Skip Materials**, all of `Tree_01` is left alone. BlendMax does not inspect individual faces and does not split the node to join only Bark01.

## Protection boundary

The important safety boundary is before `_pieces_from_node()`.

```text
plan.visible_geometry_ids
        ↓
alpha/opacity preflight
        ↓
protected? ── yes ──> exclude from joinable plan
        ↓ no
_pieces_from_node()
        ↓
existing staging / Multi/Sub splitting / bucketing / joining
```

A skipped node therefore:

- is never staged;
- is never split;
- is never bucketed;
- is never joined;
- is never recorded in `processed_originals`;
- is not deleted by the normal cleanup deletion pass.

The existing Multi/Sub face-detach implementation remains unchanged.

## Duplicate-material interaction

After a Skip decision, duplicate-material analysis runs against the filtered joinable geometry set, so skipped geometry does not create new merge candidates.

Candidates that reference a protected assigned material are also excluded from the approved merge set. This ensures **Skip** does not merge that material into another material elsewhere in the same operation.

No global post-import deduplication is attempted.

## All-protected case

If Skip protects every source geometry node, the exporter reports an informational no-op and performs no destructive cleanup rather than raising the generic "No material-bearing mesh faces were available to join" error.

## UI behavior

The current cleanup confirmation API (`rt.queryBox`) is boolean, so the three-way decision is implemented as an explicit chained flow:

1. First dialog: choose **Skip Materials** or continue.
2. Second dialog: choose **Merge Anyway** or cancel the export.

The second dialog explicitly explains that choosing No cancels the operation, so Merge and Cancel remain distinguishable.

## Completion summary

When cleanup executes with protected geometry, the completion notification includes:

```text
Alpha/Opacity materials protected: N
Geometry kept separate: N
```

## Tests added

`tests/test_alpha_opacity.py` covers:

- Standard enabled opacity map;
- Standard disabled opacity map;
- Standard constant opacity below 100;
- V-Ray enabled opacity map;
- V-Ray disabled opacity map;
- nested Multi/Sub opacity detection;
- no-op behavior when no findings exist.

## Research basis

Autodesk documents Standard material opacity/opacity-map state and Multi/Sub-Object material structure. Chaos documents the V-Ray opacity-map workflow for leaf cutouts.

See `docs/ALPHA_OPACITY_RESEARCH_NOTES.md` for the source links.

## Out of scope

- face-level alpha isolation;
- splitting a Multi/Sub node specifically to preserve alpha faces;
- Blender `.001` material deduplication;
- material rename cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.
