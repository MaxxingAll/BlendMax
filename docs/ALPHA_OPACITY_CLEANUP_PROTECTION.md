# Alpha/Opacity Cleanup Protection

Implemented on `feat/alpha-opacity-cleanup-protection`.

The cleanup now performs a non-mutating alpha/opacity preflight before material analysis and execution. Detection uses actual material/map state rather than material names.

## Rules

- Standard: enabled `opacityMap` (`opacityMapEnable`) or `opacity < 100`.
- V-Ray: enabled `texmap_opacity` / `texmap_opacity_on` path.
- Present-but-disabled opacity maps do not trigger protection by themselves.
- Refraction alone is not treated as alpha/opacity protection.
- Detection recursively walks sub-material and sub-texture graphs.

For Multi/Sub, any nested qualifying alpha/opacity path protects the entire assigned geometry node. No face-level inspection or splitting is introduced.

## User choices

One consolidated warning is shown when affected geometry is found:

- **Skip Materials** — keep the entire affected source geometry separate and keep its material graph out of destructive material merging for this operation.
- **Merge Anyway** — use the existing cleanup path.
- **Cancel Export** — stop before execution.

Because the current Max confirmation API is boolean-only, the three-way flow uses two explicit prompts so Merge and Cancel cannot be confused.

## Safety boundary

Skip filters the cleanup plan before `_pieces_from_node()`:

```text
visible geometry
    ↓
alpha/opacity preflight
    ↓
protected → exclude from joinable plan
    ↓
_pieces_from_node()
    ↓
existing staging / Multi/Sub splitting / bucketing / joining
```

A protected node is therefore never staged, split, bucketed, joined, or recorded for original-node deletion.

## Material merge handling

Duplicate-material analysis runs only on joinable geometry. Candidates containing protected material-graph IDs are also rejected from the approved merge set.

## All-protected case

If all source geometry is protected, cleanup returns a clean informational no-op rather than the previous `No material-bearing mesh faces were available to join` error.

## Validation

`tests/test_alpha_opacity.py` covers Standard/V-Ray map states, constant Standard opacity, recursive Multi/Sub detection, and the no-findings decision path. Full host validation still requires running the cleanup inside the supported 3ds Max/V-Ray environment.

## Research

- Autodesk Standard material opacity/map API: https://help.autodesk.com/cloudhelp/2025/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57F5EBBA-5F54-4CD4-8993-0B07A3571293.html
- Autodesk Multi/Sub-Object API: https://help.autodesk.com/cloudhelp/2021/ENU/3DSMax-MAXScript/files/GUID-7ECB1E85-6199-4143-BEDA-3B26DD35E0C3.htm
- Chaos V-Ray leaf opacity workflow: https://docs.chaos.com/display/VMAX/How%2Bto%2BMake%2BLeaves

## Out of scope

- face-level alpha isolation;
- partial Multi/Sub splitting;
- Blender `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.
