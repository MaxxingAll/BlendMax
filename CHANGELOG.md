# BlendMax Changelog

This file records user-visible changes to the 3ds Max exporter/cleanup and the
Blender importer. BlendMax is still alpha software; host-tested baselines are
called out separately from automated coverage.

## Blender Importer (unreleased)

### Added

- Resolves manifest parameter names case-insensitively while preserving their
  exact spelling, so casing variations can no longer silently fall back to
  default values and distinct property names cannot collapse into one another.
  Known cross-release spellings can be registered in an explicit alias table
  instead of relying on implicit punctuation stripping.
- Reports every captured `VRayMtl` parameter that has no Blender shader mapping
  as a warning, deduplicated per parameter name. Connected-texture map controls
  are excluded because they are already interpreted through the generic slot
  handling. This surfaces untested parameter aliases during the production
  audit instead of discarding them quietly.
- Maps V-Ray `VRayMtl` anisotropy, sheen, and thin film to native Principled
  BSDF inputs. Anisotropy magnitude becomes Blender's Anisotropic input, with a
  quarter turn added for negative (perpendicular) V-Ray values and the 0..1
  rotation passed through as Blender's 0..1 full-circle Anisotropic Rotation.
  Sheen color's luminance drives Sheen Weight (V-Ray has no separate sheen
  weight), its glossiness is inverted to Sheen Roughness, and its color maps to
  Sheen Tint. Thin-film IOR maps directly, and thickness collapses the V-Ray
  min/max range to the minimum (matching V-Ray's no-blend-map behavior), with a
  disabled thin film mapping to zero thickness.
- Maps V-Ray coat color to Coat Tint, `diffuse_roughness` to Diffuse Roughness,
  and thin-walled refraction to Blender's Thin Wall flag. V-Ray's separate
  coat-darkening effect has no Blender equivalent and remains reported as
  unmapped.
- Reports a material whose refraction glossiness diverges from its reflection
  glossiness: Blender's Principled shader exposes one roughness for both, so
  the reflection roughness is used and the refraction roughness is flagged as
  an approximation. V-Ray keeps refraction as glossiness even when "Use
  roughness" is enabled, so the comparison always inverts refraction
  glossiness to roughness first.

### Host evidence

- Pending Blender 5.2 verification of the new anisotropy, sheen, thin-film,
  coat, diffuse-roughness, and thin-walled-refraction mappings against a real
  `VRayMtl` asset.
- The negative-anisotropy quarter-turn and sheen-luminance-as-weight
  conversions are treated as unsettled inferences: unit-tested, but requiring a
  brushed-metal anisotropy A/B and a white/saturated/equal-luminance sheen A/B
  in Max and Blender before they are considered verified.

## Blender Importer 0.1.4 — 2026-08-26

### Fixed

- Removes synthetic or otherwise undeclared objects created by Blender's FBX
  importer instead of retaining them inside the imported asset.
- Removes the discarded object's orphaned mesh/curve data where applicable.

### Host evidence

- Importer 0.1.3 eliminated all 27 unsupported-PhysicalMaterial warnings from
  the Ring-Light package and reconstructed 26 materials.
- That pass exposed one undeclared `Untitled` FBX object; the 0.1.4 correction
  removed the object and its large cube during the Blender 5.2 retest.
- Ring-Light completed with 26 objects, 26 native materials, no warnings or
  errors, visible packaged textures, and intact hierarchy/world-origin
  placement.
- All 99 automated project tests pass.

## Blender Importer 0.1.3 — 2026-08-26

### Added

- Translates 3ds Max `PhysicalMaterial` graphs to native Principled BSDF
  shaders instead of magenta fallbacks.
- Maps base color/weight, reflectivity, roughness and its invert state,
  metalness, transparency, IOR, thin-wall state, emission, coat, sheen,
  anisotropy, SSS weight, thin film, bump, and cutout values.
- Resolves exported Physical Material map-enable controls and wires supported
  base-color, weight, reflectivity, roughness, metalness, transparency,
  emission, coat, bump, and cutout maps.

### Automated validation

- Parsed the production Ring-Light package: 26 Physical Materials and two
  packaged Bitmaptexture base-color links enter the native translation path
  without fallback warnings.
- All 97 automated project tests pass. Blender 5.2 host validation remains
  pending.

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
