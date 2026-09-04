# BlendMax Changelog

This file records user-visible changes to the 3ds Max exporter/cleanup and the
Blender importer. BlendMax is still alpha software; host-tested baselines are
called out separately from automated coverage.

## Blender Importer 0.1.7 — 2026-09-04

### Added

- Adds a structured **BlendMax Import Complete** popup after successful imports.
- Shows object, material, packaged-texture, warning, and compatibility-note counts in one place.
- Separates actionable warnings from known compatibility notes while retaining the detailed console output for debugging.
- Shows an explicit clean-import confirmation when no warnings or notes were generated.

### Release metadata

- Bumps the Blender importer and extension manifest version to **0.1.7**.

### Verification

- Added bpy-free coverage for the UI-neutral summary payload.
- Existing importer diagnostics and console reporting remain unchanged.

## Blender Importer 0.1.6 — 2026-09-04

### Added

- Adds a compact **⚠ Restart Blender** notice in BlendMax Add-on Preferences
  when a one-restart refresh is pending. Hovering the control explains that a
  Blender restart applies recent BlendMax changes and clears the notice
  automatically after the next Blender process starts.
- Stores the one-restart state in Blender's user configuration resource path so
  the notice survives the current Blender session and is consumed after restart.

### Release metadata

- Bumps the Blender importer and extension manifest version to **0.1.6**.

### Verification

- Clean Blender 5.2 runtime re-import passed with one genuine missing-texture
  warning, one grouped unsupported-parameter note, one grouped glossiness note,
  and no per-field VRayMtl warning spam.
- Refraction/reflection diagnostics honor `brdf_useRoughness`: equal values in
  roughness mode stay silent, while divergent values remain grouped as an
  approximation note.
