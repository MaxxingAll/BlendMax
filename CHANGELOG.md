# BlendMax Changelog

This file records user-visible changes to the 3ds Max exporter/cleanup and the
Blender importer. BlendMax is still alpha software; host-tested baselines are
called out separately from automated coverage.

### Verification

- Clean Blender 5.2 runtime re-import passed with one genuine missing-texture
  warning, one grouped unsupported-parameter note, one grouped glossiness note,
  and no per-field VRayMtl warning spam.
- Refraction/reflection diagnostics honor `brdf_useRoughness`: equal values in
  roughness mode stay silent, while divergent values remain grouped as an
  approximation note.

## Max Exporter 0.1.0-alpha.4.3.0 — 2026-09-03

### Changed

- Adds alpha/opacity protection to the cleanup workflow so affected source geometry can be skipped instead of being joined.
- Adds recursive Standard, Physical Material Cutout, and V-Ray opacity-map detection with conservative failure handling.
- Adds cleanup-entrypoint regression coverage for Skip/Merge/Cancel boundaries and mixed protected/unprotected scenes.

### Release metadata

- Bumps the Max exporter and AppBundle version so the alpha/opacity cleanup protection change is identifiable in installed builds.

## Max Exporter 0.1.0-alpha.4.2.0 — 2026-09-02

### Changed

- Raises the grouped-asset export payload limit from **30 to 500 geometry nodes**.
- Boundary coverage accepts 500 objects and rejects 501.

### Release metadata

- Bumps the Max exporter and AppBundle version so the user-visible limit change is identifiable in installed builds.

## Blender Importer 0.1.5 — 2026-09-02
