# BlendMax Blender Importer 0.1.5 Test Matrix

## Scope

Primary tested target: Blender 5.2. Minimum declared version: Blender 4.2.0. No
maximum Blender version is declared; API variation is contained in the Blender
adapter through operator, socket, and property feature detection.

The importer has no timer, background service, persistent handler, or external
Python dependency. Each import performs one archive scan, selective extraction,
one FBX operator call, and indexed O(n) manifest/graph processing.

## Automated status

The current automated suite contains **133 tests** under ordinary Python.
GitHub Actions runs the suite on Python 3.11, 3.12, and 3.13. The suite covers
Blender packaging/manifest behavior, importer translation, V-Ray parameter and
map contracts, diagnostics grouping, Max cleanup/export validation, and the
existing installer/update paths.

The headless V-Ray fixtures are deliberately simulated manifests, not claims
that a running V-Ray host produced those exact values. They provide a fast
regression layer for the importer pipeline; real Max/V-Ray A/B tests remain the
ground truth for renderer-specific host behavior.

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

## Verified V-Ray host parameter adaptation

The requested real 3ds Max/V-Ray + Blender checks are complete. The milestone
acceptance criterion is correct BSDF parameter adaptation; renderer-specific
visual parity is not required for these three checks.

### 1. Negative V-Ray anisotropy → +0.25 rotation — PASS

A real `VRayMtl` with `anisotropy = -0.5` and
`anisotropy_rotation = 0.0` imported to Blender with:

- **Anisotropic = 0.5**
- **Anisotropic Rotation = 0.25**

### 2. Sheen Weight = luminance of `sheen_color` — PASS

Real host checks produced:

- white sheen → Weight `1.000`, white tint
- saturated red sheen → Weight `0.213`, red tint
- green `(0, 0.297, 0)` → Weight `0.212`, green tint

### 3. Live Max parameter casing — PASS

Live `getPropNames` confirmed these actual keys and readable values:

- `#reflection_glossiness`
- `#refraction_glossiness`
- `#brdf_useRoughness`
- `#selfIllumination`

## Final runtime gate

One clean Blender 5.2 re-import of the previously noisy test asset remains to be
performed against the current `0.1.5` build. The expected operator-facing result
is:

1. one grouped note for known unsupported V-Ray fields;
2. one grouped note for divergent reflection/refraction glossiness;
3. a missing packaged image remains a genuine warning; and
4. no per-field `BlendMax warning: VRayMtl parameter ...` spam.

This is a runtime acceptance check, not something the ordinary-Python suite can
prove.

## Pass criteria

- Import completes without a Python traceback.
- Relative object transforms, hierarchy, UVs, normals, tangents, and material
  indices visually match the FBX/export manifest after world-origin placement.
- No unpacked image points at the importer's temporary directory.
- The original manifest is present in Blender's Text data and referenced by the
  asset controller.
- Warnings identify real problems; expected unsupported/approximate V-Ray
  behavior is grouped into informational notes.
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
  reflection/refraction roughness; divergent values are grouped as an
  informational note rather than reproduced exactly.
- Advanced rendering parity beyond the verified Basketball and four-potted-
  plants baselines remains ongoing.
