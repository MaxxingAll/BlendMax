# Alpha/Opacity Cleanup Protection

## Status

Implemented on `feat/alpha-opacity-cleanup-protection`.

## Purpose

Prevent **Join Mesh by Material** cleanup from altering the appearance of geometry whose assigned material graph uses alpha/opacity behavior.

When **Skip Materials** is selected, the entire affected source geometry node remains separate. No face-level isolation is attempted.

## Detection rules

Detection uses actual material/map state, never material names.

### Standard Material

Flag the assigned geometry when:

- `opacityMap` is populated and `opacityMapEnable` is true; or
- `opacity` is below 100.

A populated but disabled opacity map does not trigger protection by itself. Reduced constant opacity does trigger protection because it changes appearance.

### V-Ray Material

Flag the assigned geometry when the V-Ray material exposes an opacity map that is enabled:

- `texmap_opacity`
- `texmap_opacity_on`

A present-but-disabled opacity map does not trigger protection by itself. Refraction alone is not classified as alpha/opacity protection.

### Recursive graph / Multi/Sub

The detector recursively walks assigned materials, sub-materials, and sub-textures. If any nested path contains qualifying alpha/opacity behavior, the **entire source geometry node** is flagged.

For a Multi/Sub material, whole-node protection is deliberate:

```text
Tree_01
└─ Multi/Sub
   ├─ Bark01
   └─ Leaves01
      └─ Opacity map
```

With **Skip Materials**, all of `Tree_01` stays separate. We do not inspect faces or split it to save Bark01.

## User interaction

When findings exist, one consolidated warning explains that alpha/opacity can control which parts of a mesh are visible and that joining may alter appearance.

The current Max runtime confirmation API is boolean-only, so the three choices use a deterministic chained flow:

1. First dialog: **Skip Materials** or continue.
2. Second dialog: **Merge Anyway** or cancel the export.

### Skip Materials

Exclude the affected geometry and its assigned material graph from this cleanup operation. The source node never enters staging, Multi/Sub detachment, bucketing, joining, or original-node deletion.

### Merge Anyway

No protection is applied; the existing cleanup path processes the affected geometry.

### Cancel Export

Return before `execute()` is called.

## Protection boundary

The entry point filters `plan.visible_geometry_ids` into a joinable plan before the destructive adapter runs:

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

The existing `_pieces_from_node()` Multi/Sub splitter therefore remains unchanged.

## Material merge protection

Duplicate-material analysis runs on the filtered joinable geometry set. Candidates containing protected material-graph IDs are also rejected from the approved material-merge set, so Skip does not merge the detected material graph into another material during the same operation.

## All-protected case

If Skip protects every geometry node, BlendMax reports an informational no-op and performs no destructive cleanup. Original geometry and materials remain intact.

## Completion summary

Executed cleanup reports:

```text
Alpha/Opacity materials protected: N
Geometry kept separate: N
```

## Tests

`tests/test_alpha_opacity.py` covers:

- Standard enabled opacity map;
- Standard disabled opacity map;
- Standard constant opacity below 100;
- V-Ray enabled opacity map;
- V-Ray disabled opacity map;
- nested Multi/Sub opacity detection;
- no-findings decision behavior.

## Research basis

Autodesk documents Standard material opacity/opacity-map state and Multi/Sub-Object material structure. Chaos documents the V-Ray opacity-map workflow for leaf cutouts.

See `docs/ALPHA_OPACITY_RESEARCH_NOTES.md` for the source links.

## Out of scope

- face-level alpha isolation;
- partial Multi/Sub splitting;
- Blender `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.
