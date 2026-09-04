# Material Compatibility Contract

BlendMax keeps material translation code separate from the classification of known compatibility gaps.

The shared registry lives in `blendmax_blender/material_compatibility.py`.

## Rules

- Material class matching is case-insensitive.
- The registry contains only **known intentional gaps**; it is not the source of truth for conversion itself.
- Translators remain responsible for reading parameters and constructing Blender node graphs.
- Known gaps are eligible for grouped informational notes instead of per-field warnings.
- Unknown material classes and newly introduced exporter parameters must remain visible to diagnostics rather than being silently treated as supported.

## Current registrations

- `VRayMtl`: known Principled-translation gaps are registered and grouped by the importer diagnostics layer.
- `PhysicalMaterial`: the registry is intentionally empty for now. Its translator already exists; future Physical Material fidelity work will add verified gaps here rather than assuming unimplemented properties are equivalent.

This contract is deliberately small so new material families can be added without introducing a renderer-specific class hierarchy or rewriting the existing translators.
