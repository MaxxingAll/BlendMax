# BlendMax Alpha.3.4 Test Matrix

Status: **Max exporter active development — Blender importer deferred**

## Reference environment

- Autodesk 3ds Max 2025.3
- V-Ray 7.00.02
- BlendMax Max Exporter 0.1.0-alpha.3.4
- BlendMax manifest schema 0.1.1
- FBX binary, Z-up, metres, animation disabled

The manual material tests below were performed with one isolated `VRayMtl`
asset through Alpha.3.2. Alpha.3.3 repaired the Reflection Roughness control
alias and texture-to-package references. Alpha.3.4 continues Max exporter
development with isolated group selection.

Manual evidence packages are not committed because they contain user-provided
textures. Their filenames are recorded here so results can be traced to the
original test session.

## Core VRayMtl matrix

| Feature | Evidence package | Captured values and graph | Result |
| --- | --- | --- | --- |
| Diffuse map | `TestBox(3).blendmax` | `Diffuse` slot index 1; `VRayBitmap`; map enabled; multiplier 100%; bitmap copied | Pass |
| Reflection Roughness map | `TestBox(4).blendmax` | `Reflection roughness` slot index 5; `VRayBitmap`; map disabled; multiplier 37%; explicit graph/package link; bitmap copied | Pass with Alpha.3.3 |
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

## Exporter regression checks

| Check | Automated result | 3ds Max result |
| --- | --- | --- |
| Reflection Roughness map disabled, multiplier 37% | Pass | Pass with `TestBox(4).blendmax` |
| Relative bitmap path links graph node/property to packaged texture | Pass | Pending |
| Duplicate bitmap filenames receive distinct package paths | Pass | Pass with `TestBox_TEST3_R02.blendmax`; two different `FAN.png` files produced distinct content hashes, `FAN.png` and `FAN_7d446767.png`, with correct slot ownership |
| Disconnected/stale global bitmap is not packaged | Pass by graph-only collection | Pending |
| Grouped geometry excludes a light/helper from object records | Pass | Pass with `TestBox_TEST2_R01.blendmax`; FBX contains only the group root and two meshes |
| Closed group temporarily opens and restores its original state | Pass | Export passed; final Max UI state confirmation pending |
| FBX selection contains geometry payload only, not the group head | Pass | Pass; FBX retained the renamed group root only as the required ancestor and excluded its ignored siblings |
| Unexpected Max selection expansion aborts before FBX export | Pass | Pending |
| Geometry below an ignored helper is reparented to the exported group | Pass | Pending |
| Existing FBX settings restored after success | Pass | Pending |
| Existing FBX settings restored after export failure | Pass | Pending |
| Shape nodes excluded from the v0.1 geometry contract | Pass | Pending |

## Automated regression suite

Alpha.3.4 passes 35 automated tests covering:

- one-object and one-group scene rules;
- the 15-object group limit;
- tiny and oversized asset policies;
- material graph serialization and parameter pruning;
- V-Ray version compatibility from 7.00.x through 7.40.x;
- graph-owned bitmap collection, relative paths, duplicate filenames, and
  package creation;
- ignored group descendants and exported-parent normalization;
- closed-group isolation, selection verification, and state restoration after
  successful and failed exports;
- V-Ray Reflection Roughness/Glossiness map-control aliases;
- FBX exporter setting restoration on success and failure;
- AppBundle construction and exact-bundle replacement;
- safe ZIP update extraction and rollback behavior;
- 3ds Max 2025 manifest component categories; and
- isolated `python.ExecuteFile` launcher imports.

Run the suite from the project root:

```bash
python -m unittest discover -s tests -v
```

## Future importer contract tracking

The Blender importer is not being implemented yet. These fields are tracked so
the Max exporter can develop toward a clear future input contract:

- manifest schema version `0.1.1`;
- graph nodes identified by stable per-package IDs and `material` or `texture`
  kinds;
- material and texture connections represented by `sub_materials` and
  `sub_textures` references;
- V-Ray colours serialized as RGBA values from 0 to 1;
- each `textures` record linking `graph_node_id` and `parameter` to `raw_path`,
  resolved `source_path`, and collision-safe `package_path`;
- only graph-reachable textures included in the package;
- geometry-only object payloads, with ignored nodes omitted from object records;
- geometry delivered as binary FBX in metres with Z up; and
- unsupported advanced materials remaining outside the current v0.1 scope.

No exporter freeze is currently planned. Scene handling, additional material
properties, and other Max-side improvements may continue before Blender
importer development begins. Advanced compound materials remain deferred until
the core exporter is mature.
