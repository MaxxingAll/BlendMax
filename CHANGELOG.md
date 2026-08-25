# BlendMax Changelog

This file records user-visible changes to the 3ds Max exporter/cleanup and the
Blender importer. BlendMax is still alpha software; host-tested baselines are
called out separately from automated coverage.

## Max Exporter 0.1.0-alpha.4.1.0 — 2026-08-25

### Added

- Detects separate cleanup materials that share a normalized name.
- Builds conservative SHA-256 fingerprints from material class, readable
  parameters, sub-material slots, texture-map slots, and recursive graph
  structure.
- Captures every readable Physical Material value. V-Ray comparison includes
  conversion-relevant parameters, map controls, and the same recursive graph.
- Offers a confirmation for each structurally identical same-name set.
- Creates one copied `<name>_MERGED` material for an approved set and resolves
  its faces to one output material mesh.
- Keeps same-name materials with different classes, values, or nested maps
  separate. Refusing a merge also preserves the original identities.

### Verified

- 3ds Max 2025.3 ring-light host pass: 74 input meshes became 26 output meshes.
- Five identical material sets were merged, replacing ten original material
  assignments.
- 141 imported Shape/segment objects were deleted through the existing safety
  confirmation.
- All 92 automated project tests pass.

## Max Exporter 0.1.0-alpha.4.0.1 — 2026-08-25

### Fixed

- Requires one opened root-group head selected through its pink group box.
- Replaced the ambiguous root-selection error with explicit pink-box guidance.
- Detects Shape/Spline/Line descendants and zero-polygon imported linework.
- Added the separate Shape deletion confirmation and refusal error.
- Purges stale `blendmax_max` modules before menu actions so installed Python
  updates do not continue executing an older in-memory core.
- Bumped both the friendly and Autodesk AppBundle versions so downloaded and
  installed builds can be distinguished reliably.

### Verified

- Ring-light host pass: 74 input meshes became 31 material meshes before
  duplicate-material merging was added.
- 141 Shape/segment objects were detected and deleted while retaining the root.

## Max Exporter 0.1.0-alpha.4.0 — 2026-08-25

### Added

- Added **Cleanup > Join Mesh by Material...** for hierarchy-heavy SketchUp
  assets.
- Splits Multi/Sub faces through explicit `materialIDList` values and joins by
  actual material identity rather than display name.
- Builds replacement geometry on copies before deleting source nodes.
- Removes nested groups while retaining the selected root in one undoable
  operation.
- Stops export and cleanup when any scene object is hidden or frozen.

## Blender Importer 0.1.2 — 2026-08-25

### Added

- Installable Blender extension with **File > Import > BlendMax Asset**.
- Safe `.blendmax` validation and selective archive extraction.
- One-pass FBX import followed by indexed manifest/hierarchy reconstruction.
- World-origin placement that centers the footprint, grounds the asset at Z=0,
  and avoids applying the same translation twice to nested children.
- Multi/Sub material-slot reconstruction and Principled BSDF conversion for the
  current `VRayMtl` feature set.
- Recursive handling for `VRay2SidedMtl`, `Bitmaptexture`, `VRayBitmap`,
  `Normal_Bump`, `VRayColor`, and basic `Noise`.
- Packed images, stored source manifest, magenta unsupported-shader fallback,
  and cleanup of failed import attempts.
- Deterministic extension ZIP builder targeting Blender 4.2 or newer with no
  declared maximum version.

### Verified

- Basketball: mesh, two material slots, diffuse/normal wiring, and grounded
  world-origin placement passed in Blender 5.2.
- Four potted plants: 12 meshes, hierarchy, Multi/Sub, `VRay2SidedMtl`, packed
  images, procedural bump, reconstructed pivots, and world-origin placement
  passed in Blender 5.2.

## Max Exporter 0.1.0-alpha.3.6 — 2026-08-20

- Raised the grouped-asset limit from 15 to 30 geometry nodes.
- Retained the 31-object rejection boundary.
- Verified the limit against the four-potted-plants production asset.

## Max Exporter 0.1.0-alpha.3.5 — 2026-08-19

- Replaced conservative rotated-node bounds with evaluated world-space mesh
  bounds and retained a safe node-bound fallback.
- Deletes temporary mesh snapshots immediately after measurement.

## Max Exporter 0.1.0-alpha.3.4 — 2026-08-19

- Temporarily opens closed groups for isolated FBX selection and restores their
  original state afterward.
- Rejects unexpected Max selection expansion before export.

## Max Exporter 0.1.0-alpha.3.3 — 2026-08-18

- Preserved Reflection Roughness/Glossiness map controls.
- Limited texture packaging to graph-reachable maps.
- Added explicit graph-node/property ownership for packaged textures.
- Restored FBX exporter settings after success and failure.
- Formalized the geometry-only v0.1 contract and manifest schema 0.1.1.

## Max Exporter 0.1.0-alpha.3.2 — 2026-08-18

- Fixed installed menu launchers under `python.ExecuteFile`.
- Established the persistent menu/export baseline used by subsequent tests.

## Max Exporter 0.1.0-alpha.3.1 — 2026-08-18

- Corrected 3ds Max 2025 AppBundle component categories and menu registration.

## Max Exporter 0.1.0-alpha.3 — 2026-08-18

- Preserved separate Fresnel and refraction IOR values and the IOR-lock state.
- Expanded the verified core `VRayMtl` material feature set.

## Max Exporter 0.1.0-alpha.2 — 2026-08-14

- Published the initial Python-first 3ds Max exporter and `.blendmax` package.
- Added compatibility handling for 3ds Max 2025.3 and V-Ray 7.00.x–7.40.x.
