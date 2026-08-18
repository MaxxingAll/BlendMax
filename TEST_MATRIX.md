# BlendMax Alpha.3.2 Test Matrix

Status: **Max-side baseline frozen**

Freeze date: 2026-08-18

## Reference environment

- Autodesk 3ds Max 2025.3
- V-Ray 7.00.02
- BlendMax Max Exporter 0.1.0-alpha.3.2
- BlendMax manifest schema 0.1.0
- FBX binary, Z-up, metres, animation disabled

The material tests below were performed with one isolated `VRayMtl` asset.
Alpha.2 evidence packages test the same material serializer retained by
Alpha.3.2. The final menu, Opacity, Self-Illumination, and Normal Map tests were
exported end to end with Alpha.3.2.

Manual evidence packages are not committed because they contain user-provided
textures. Their filenames are recorded here so results can be traced to the
original test session.

## Core VRayMtl matrix

| Feature | Evidence package | Captured values and graph | Result |
| --- | --- | --- | --- |
| Diffuse map | `TestBox(3).blendmax` | `Diffuse` slot index 1; `VRayBitmap`; map enabled; multiplier 100%; bitmap copied | Pass |
| Reflection Roughness map | `TestBox(3).blendmax` | `Reflection roughness` slot index 5; `VRayBitmap`; bitmap copied | Pass |
| Bump map | `TestBox(3).blendmax` | `Bump` slot index 4; map enabled; multiplier 30%; bitmap copied | Pass |
| Metalness | `TestBox_Metalness.blendmax` | `Metalness` slot index 20; scalar 0.75; map enabled; multiplier 65%; bitmap copied | Pass |
| Fresnel IOR | `TestBox_FresnelIOR_Patched.blendmax` | reflection IOR 2.2; refraction IOR 1.33; IOR lock disabled | Pass |
| Refraction map | `TestBox_Refraction.blendmax` | `Refraction` slot index 3; map enabled; multiplier 55%; refraction IOR 1.52; bitmap copied | Pass |
| Opacity map | `TestBox_Opacity_Menu.blendmax` | `Opacity` slot index 13; map enabled; multiplier 40%; opacity mode 1; bitmap copied | Pass |
| Self-Illumination map | `TestBox_SelfIllumination.blendmax` | `Self-illumination` slot index 18; map enabled; map multiplier 100%; material multiplier 6.5; GI enabled; bitmap copied | Pass |
| Normal map through Bump | `TestBox_NormalMap.blendmax` | `Bump` index 4 -> `VRayNormalMap` -> `Normal map` index 1 -> `VRayBitmap`; bump multiplier 45%; normal multiplier 1.0; red/green flip disabled; bitmap copied | Pass |

Every listed package contained `geometry.fbx`, `manifest.json`, its expected
textures, and zero exporter warnings for the final accepted test case.

## 3ds Max integration matrix

| Integration check | Expected result | Result |
| --- | --- | --- |
| AppBundle manifest | Loads in 3ds Max 2025.3 with the `macroscripts parts` and `post-start-up scripts parts` component categories | Pass |
| Persistent menu | Top-level **BlendMax** menu remains available after restarting 3ds Max | Pass |
| Export action | **Export Asset...** invokes the installed Python exporter | Pass |
| Update action | **Install Update from ZIP...** opens the Python ZIP updater | Pass |
| Project action | **Project Page** opens the BlendMax repository | Pass |
| About action | **About BlendMax** displays installed version information | Pass |
| Menu-to-package workflow | Alpha.3.2 menu export produces a valid `.blendmax` ZIP with FBX, manifest, and textures | Pass |

## Automated regression suite

Alpha.3.2 passes 23 automated tests covering:

- one-object and one-group scene rules;
- the 15-object group limit;
- tiny and oversized asset policies;
- material graph serialization and parameter pruning;
- V-Ray version compatibility from 7.00.x through 7.40.x;
- bitmap collection and package creation;
- AppBundle construction and exact-bundle replacement;
- safe ZIP update extraction and rollback behavior;
- 3ds Max 2025 manifest component categories; and
- isolated `python.ExecuteFile` launcher imports.

Run the suite from the project root:

```bash
python -m unittest discover -s tests -v
```

## Frozen baseline contract

The Blender importer may treat the following Alpha.3.2 behavior as its initial
input contract:

- manifest schema version `0.1.0`;
- graph nodes identified by stable per-package IDs and `material` or `texture`
  kinds;
- material and texture connections represented by `sub_materials` and
  `sub_textures` references;
- V-Ray colours serialized as RGBA values from 0 to 1;
- copied textures referenced through the manifest `textures` table;
- geometry delivered as binary FBX in metres with Z up; and
- unsupported advanced materials remaining outside the frozen v0.1 scope.

Until the first Blender importer consumes this contract, Max-side work is
limited to compatibility fixes and regressions. New material families and
advanced compound materials are deferred.
