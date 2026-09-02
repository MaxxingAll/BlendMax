# BlendMax Blender Importer 0.1.5 Test Matrix

## Scope

Primary tested target: Blender 5.2. Minimum declared version: Blender 4.2.0. No
maximum Blender version is declared; API variation is contained in the Blender
adapter through operator, socket, and property feature detection.

The importer has no timer, background service, persistent handler, or external
Python dependency. Each import performs one archive scan, selective extraction,
one FBX operator call, and indexed O(n) manifest/graph processing.

## Automated status

All 128 project tests are expected to pass under ordinary Python after the new
headless V-Ray map-contract test. Fifty-eight importer-specific tests cover:

- Blender extension metadata and root ZIP layout;
- reproducible extension builds;
- manifest schema 0.1.0 and 0.1.1 parsing;
- duplicate object-name and incompatible-schema rejection;
- legacy texture-to-graph matching by filename;
- texture-slot normalization;
- V-Ray map enable and multiplier interpretation;
- glossiness-to-roughness conversion;
- case-insensitive manifest parameter lookup that preserves exact spelling,
  its punctuation-variant rejection, and explicit-alias fallback;
- access tracking and unmapped-key reporting;
- VRayMtl dispatch, mixed-casing parameter mapping, and unmapped-parameter
  diagnostics (deduplicated per parameter);
- V-Ray anisotropy magnitude/rotation, negative-sign quarter-turn, and
  rotation wrapping;
- V-Ray sheen glossiness inversion;
- V-Ray thin-film min-thickness selection and off-to-zero mapping;
- VRayMtl anisotropy, sheen, and thin-film Principled defaults;
- VRayMtl coat tint, diffuse roughness, and thin-walled refraction defaults;
- refraction-glossiness divergence reporting and its matching no-warning case;
- simulated 3ds Max/V-Ray manifest -> ManifestIndex -> VRayMtl ->
  fake-Blender-node integration fixtures;
- headless VRayMtl bitmap/map fixture coverage for Diffuse, Reflection,
  Reflection roughness, Refraction, and Bump links, enable state, multipliers,
  packaged texture records, and slot normalization;
- the importer/exporter parameter-name contract: every literal VRayMtl
  parameter the importer reads must exist in the exporter's
  `VRAY_MTL_PROPERTIES` whitelist (or be a `texmap_*` map control), and the
  full whitelist must map or report every property;
- Physical Material class dispatch, map-enable interpretation, and roughness
  inversion;
- Physical Material Principled defaults and base-color map wiring;
- color normalization;
- world-origin footprint centering and ground-level anchoring;
- nested-group descendant bounds and hierarchy-cycle rejection;
- direct FBX-root translation without moving nested children twice;
- separation and removal of FBX objects that have no manifest record;
- selective archive extraction;
- traversal rejection;
- missing packaged-texture rejection; and
- `.blendmax` file-type validation.

The headless V-Ray fixtures are deliberately simulated manifests, not claims
that a running V-Ray host produced those exact values. They provide a fast
regression layer for the importer pipeline; real Max/V-Ray A/B tests remain the
ground truth for renderer-specific visual parity.

The package reader was also exercised successfully against the current
Basketball package, the four-potted-plants package, and the older normal-map
package. This confirms their manifests and declared payloads can enter the
import pipeline; it is not a substitute for Blender runtime rendering checks.

## Verified Blender 5.2 manual passes

### A. Basketball

1. Install `blendmax_importer-0.1.5.zip` from disk.
2. Import `Basketbalv2l.blendmax`.
3. Confirm one mesh appears in its own collection under a `[BlendMax]`
   controller.
4. Confirm the mesh has two material slots and retains its polygon material
   split.
5. Confirm the diffuse image uses sRGB, the normal image uses Non-Color, and
   both images are packed.
6. Confirm the normal image flows through a **Normal Map** node rather than a
   height **Bump** node.

### B. Four potted plants

1. Import `4pottedplants.blendmax` into a clean scene.
2. Confirm 12 meshes, the recorded nested group hierarchy, and one asset
   controller are present.
3. Confirm the controller sits at world origin, the plant footprint is centered
   around X/Y=0, its base rests at Z=0, and nested group pivots stay near their
   own geometry.
4. Confirm the Multi/Sub material retains six leaf/branch slots on its assigned
   meshes.
5. Confirm each leaf `VRay2SidedMtl` becomes a Backfacing-driven front/back
   shader mix.
6. Confirm repeated package images are reused per color-space role and packed.
7. Confirm the procedural pot bump receives a Blender Noise Texture fallback.

### C. Ring-Light Physical Materials

1. Install `blendmax_importer-0.1.5.zip` and import `RingLight.blendmax` into a
   clean scene.
2. Confirm the completion message reports 26 objects and 26 materials without
   the previous 27 unsupported-PhysicalMaterial warnings.
3. Confirm none of the materials use the magenta fallback shader.
4. Confirm the `*` and `[Metal Corrugated Shiny]1` materials load, wire, and
   pack their Base Color Map images in sRGB.
5. Confirm materials exported with `roughness=0` and `roughness_inv=true`
   receive Principled Roughness 1.0.
6. Confirm `vidro` receives Transmission Weight 0.8, IOR 1.52, and Thin Wall
   enabled.
7. Confirm the undeclared `Untitled` FBX object and its large cube are absent.

Result: passed in Blender 5.2. All 26 objects and 26 native materials imported
without warnings or errors; the two mapped materials displayed their packaged
images, the hierarchy and world-origin placement remained intact, and the
undeclared `Untitled` cube was absent.

## Pending host validation (unsettled inferences)

These conversions are implemented and unit-tested but are treated as
*unverified* until the host A/B passes below settle them. Record results (with
screenshots) here or in the PR.

### 1. Negative V-Ray anisotropy → +0.25 rotation

The branch maps a negative `anisotropy` sign to a 90° rotation because V-Ray's
sign flips the elongation axis while Blender only exposes a non-negative
magnitude. Unit and headless manifest tests cover the arithmetic; the ±90°
direction must be confirmed visually.

Procedure: create one brushed-metal `VRayMtl`, then duplicate it:

- A: `anisotropy = +0.5`, `anisotropy_rotation = 0.0`
- B: `anisotropy = -0.5`, `anisotropy_rotation = 0.0`

Export both through BlendMax, import into Blender, and compare the highlight
direction/orientation. Confirm the importer's negative-anisotropy handling
(+0.25 / 90°) matches V-Ray.

### 2. Sheen Weight = luminance of `sheen_color`

V-Ray 3ds Max has no separate sheen amount, so the color's luminance drives
Blender's Sheen Weight and the color maps to Sheen Tint. This could over- or
under-encode intensity and may double-encode the color via the tint.

Procedure: create three otherwise-identical `VRayMtl` materials:

- A: white sheen color
- B: saturated red sheen color
- C: a different sheen color with approximately the same luminance as A

Export/import and compare Max vs Blender, checking specifically for
double-encoding of intensity.

### 3. Live Max parameter-casing confirmation

Export one real `VRayMtl` with the current 3ds Max/V-Ray setup and inspect the
resulting `manifest.json`. Confirm the actual `getPropNames` keys (casefolded)
match the exporter whitelist/contract expectations for at least:

- `reflection_glossiness`
- `refraction_glossiness`
- `brdf_useRoughness`
- `selfIllumination`

This is the empirical confirmation behind the static contract and headless
fixture tests.

## Pass criteria

- Import completes without a Python traceback.
- Relative object transforms, hierarchy, UVs, normals, tangents, and material
  indices visually match the FBX/export manifest after world-origin placement.
- No unpacked image points at the importer's temporary directory.
- The original manifest is present in Blender's Text data and referenced by the
  asset controller.
- Warnings identify approximations or unsupported nodes without discarding the
  rest of the asset.
- Undo removes the imported asset as one operator action.

## Known Alpha.1 limits

- `VRayBlendMtl` and other advanced compound materials use a fallback.
- `VRay2SidedMtl` is represented as front/back surface selection; V-Ray's full
  light-translucency model is not yet reproduced.
- Normal-map red/green flip and channel-swap flags are reported but not yet
  applied.
- Bitmap crop/place controls and advanced V-Ray bitmap color transforms are
  not yet reproduced.
- V-Ray thin-film thickness uses the minimum only; a connected thickness-blend
  map is not yet interpreted, so the maximum is ignored (its value remains in
  the stored manifest).
- Blender's single Principled roughness approximates V-Ray's separate
  reflection/refraction roughness; divergent values are reported rather than
  reproduced.
- Advanced rendering parity beyond the verified Basketball and four-potted-
  plants baselines remains ongoing.
