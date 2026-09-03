# Alpha/Opacity Cleanup Protection

Implemented on `feat/alpha-opacity-cleanup-protection`.

The cleanup performs a non-mutating alpha/opacity preflight before material analysis and execution. Detection uses actual material/map state rather than material names.

## Rules

- Standard: enabled `opacityMap` (`opacityMapEnable`) or `opacity < 100`.
- Physical Material: enabled `cutout_map` / `cutout_map_on`.
- V-Ray: enabled `texmap_opacity` / `texmap_opacity_on` path.
- Present-but-disabled opacity/cutout maps do not trigger protection by themselves.
- If an opacity/cutout map enable state cannot be read after its slot is confirmed populated, detection fails closed and protects the material.
- If `getPropNames()` itself fails, detection intentionally fails open at the enumeration layer rather than guessing arbitrary renderer-specific slots.
- V-Ray constant opacity is intentionally not inferred as a cutout signal because V-Ray uses different numeric opacity semantics; this PR protects the explicit V-Ray opacity-map path instead.
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

## Adapter boundary

Alpha/opacity detection uses the adapter's public `get_node_by_id()`, `get_anim_id()`, `get_class_name()`, and `is_undefined()` accessors rather than reaching into private adapter state.

## Group handling

Protected geometry remains intact and is not passed through the join/destructive mesh path. Existing nested-group cleanup still runs on the cleanup plan, so a protected mesh can remain as a separate node while its containing nested-group structure is normalized. This is intentional for this PR: protection applies to geometry/material joining, not group-structure normalization.

**“Protected” does not preserve the surrounding nested-group hierarchy; `_remove_nested_groups()` continues to process the existing `removable_group_ids` cleanup contract.**

## Validation

- `tests/test_alpha_opacity.py` covers Standard/V-Ray map states, Physical Material Cutout, disabled-map behavior, reduced Standard opacity, explicit V-Ray constant-opacity behavior, recursive Multi/Sub detection, case-insensitive property access, `getPropNames()` enumeration failure, prompt failure, and the no-findings decision path.
- `tests/test_cleanup_entrypoint.py` covers the existing merge path plus Merge Anyway, Cancel-before-execute, and mixed-scene filtering boundaries.
- Full validation still requires repository CI plus live 3ds Max/V-Ray host validation.

## Research

See `docs/ALPHA_OPACITY_RESEARCH_NOTES.md` for direct Autodesk and Chaos references, including Physical Material Cutout.

## Out of scope

- face-level alpha isolation;
- partial Multi/Sub splitting;
- Blender `.001` material deduplication;
- material renaming cleanup;
- alpha shader conversion/rebuilding;
- V-Ray material conversion changes;
- Shapes Purge changes.
