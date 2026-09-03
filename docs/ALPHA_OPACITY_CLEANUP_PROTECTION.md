# Alpha/Opacity Cleanup Protection

Implemented on `feat/alpha-opacity-cleanup-protection`.

The cleanup now performs a non-mutating alpha/opacity preflight before material analysis and execution. Detection uses actual material/map state rather than material names.

## Rules

- Standard: enabled `opacityMap` (`opacityMapEnable`) or `opacity < 100`.
- Physical Material: enabled `cutout_map` / `cutout_map_on`.
- V-Ray: enabled `texmap_opacity` / `texmap_opacity_on` path.
- Present-but-disabled opacity/cutout maps do not trigger protection by themselves.
- If an opacity/cutout map enable state cannot be read, detection fails closed and protects the material.
- Refraction alone is not treated as alpha/opacity protection.
- Detection recursively walks sub-material and sub-texture graphs with cycle/depth protection.

For Multi/Sub, any nested qualifying alpha/opacity path protects the entire assigned geometry node. No face-level inspection or splitting is introduced.

## User choices

One consolidated warning is shown when affected geometry is found:

- **Skip Materials** — keep the entire affected source geometry separate and keep its material graph out of destructive material merging for this operation.
- **Merge Anyway** — use the existing cleanup path.
- **Cancel Export** — stop before execution.

Because the current Max confirmation API is boolean-only, the three-way flow uses two explicit prompts. The first prompt states that `No` advances to a second prompt where `Yes` means Merge Anyway and `No` means Cancel Export. Prompt failures are also treated as Cancel and surfaced with a notification.

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

## Group handling

Protected geometry remains intact and is not passed through the join/destructive mesh path. Existing nested-group cleanup still runs on the cleanup plan, so a protected mesh can remain as a separate node while its containing nested group hierarchy is removed. This is intentional for this PR: protection applies to geometry/material joining, not group-structure normalization.

## All-protected case

If all source geometry is protected, cleanup returns a clean informational no-op rather than the previous `No material-bearing mesh faces were available to join` error.

## Validation

- `tests/test_alpha_opacity.py` covers Standard/V-Ray map states, Physical Material Cutout, constant Standard opacity, recursive Multi/Sub detection, case-insensitive Standard property access, prompt-failure cancellation, and the no-findings decision path.
- `tests/test_cleanup_entrypoint.py` covers the existing merge path plus explicit Merge Anyway, Cancel-before-execute, and mixed-scene filtering boundaries.
- Full host validation still requires running the cleanup inside the supported 3ds Max/V-Ray environment.

## Research

- Autodesk Standard material opacity/map API: https://help.autodesk.com/cloudhelp/2025/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57F5EBBA-5F54-4CD4-8993-0B07A3571293.html
- Autodesk Physical Material Cutout properties: https://help.autodesk.com/cloudhelp/2022/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57562F6A-A8A1-4A28-BAE1-0D4729411214.html
- Autodesk Physical Material Cutout workflow: https://help.autodesk.com/cloudhelp/2020/ENU/3DSMax-Lighting-Shading/files/GUID-65AFACA5-59BD-4731-B384-431E166B2B12.htm
- Autodesk Multi/Sub-Object API: https://help.autodesk.com/cloudhelp/2021/ENU/3DSMax-MAXScript/files/GUID-7ECB1E85-6199-4143-BEDA-3B26DD35E0C3.htm
- Chaos V-Ray leaf opacity workflow: https://docs.chaos.com/display/VMAX/How%2Bto%2BMake%2BLeaves

## Detection decisions

- V-Ray numeric opacity is intentionally not treated as a cutout signal; protection is keyed to the explicit V-Ray opacity-map state.
- `getPropNames()` enumeration failure is intentionally fail-open at the property-enumeration layer: the detector does not guess arbitrary properties, while known slots are detected normally when Max exposes them.

## Out of scope

- face-level alpha isolation;
- partial Multi/Sub splitting;
- Blender `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.
