# BlendMax Blender Importer 0.1.2 Test Matrix

## Scope

Primary tested target: Blender 5.2. Minimum declared version: Blender 4.2.0. No
maximum Blender version is declared; API variation is contained in the Blender
adapter through operator, socket, and property feature detection.

The importer has no timer, background service, persistent handler, or external
Python dependency. Each import performs one archive scan, selective extraction,
one FBX operator call, and indexed O(n) manifest/graph processing.

## Automated status

All 92 project tests pass under ordinary Python. Twenty-two importer-specific
tests cover:

- Blender extension metadata and root ZIP layout;
- reproducible extension builds;
- manifest schema 0.1.0 and 0.1.1 parsing;
- duplicate object-name and incompatible-schema rejection;
- legacy texture-to-graph matching by filename;
- texture-slot normalization;
- V-Ray map enable and multiplier interpretation;
- glossiness-to-roughness conversion;
- color normalization;
- world-origin footprint centering and ground-level anchoring;
- nested-group descendant bounds and hierarchy-cycle rejection;
- direct FBX-root translation without moving nested children twice;
- selective archive extraction;
- traversal rejection;
- missing packaged-texture rejection; and
- `.blendmax` file-type validation.

The package reader was also exercised successfully against the current
Basketball package, the four-potted-plants package, and the older normal-map
package. This confirms their manifests and declared payloads can enter the
import pipeline; it is not a substitute for Blender runtime rendering checks.

Manual status: Basketball material reconstruction and direct world-origin
placement passed. Four potted plants passed its object/image counts, procedural
bump, Multi/Sub, VRay2Sided, direct world-origin placement, and reconstructed
pivot checks.

## Verified Blender 5.2 manual passes

### A. Basketball

1. Install `blendmax_importer-0.1.2.zip` from disk.
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
- Advanced rendering parity beyond the verified Basketball and four-potted-
  plants baselines remains ongoing.
