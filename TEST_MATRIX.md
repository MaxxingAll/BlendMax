# BlendMax Alpha.4.1.0 Test Matrix

Status: **Alpha.4.1.0 Max cleanup and duplicate-material merge host pass**

## Reference environment

- Autodesk 3ds Max 2025.3
- V-Ray 7.00.02
- BlendMax Max Exporter 0.1.0-alpha.4.1.0
- BlendMax manifest schema 0.1.1
- FBX binary, Z-up, metres, animation disabled

The manual material tests below were performed with one isolated `VRayMtl`
asset through Alpha.3.2. Alpha.3.3 repaired the Reflection Roughness control
alias and texture-to-package references. Alpha.3.4 added isolated group
selection. Alpha.3.5 replaced conservative rotated node bounds with exact
evaluated-mesh bounds while keeping a safe fallback. Alpha.3.6 raises the
grouped-asset geometry limit from 15 to 30 objects. Alpha.4.0 adds the explicit
Join Mesh by Material cleanup and a strict hidden/frozen-object preflight.

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
| Cleanup submenu | **Cleanup > Join Mesh by Material...** is registered through the persistent menu | Pass in 3ds Max 2025.3 |
| Cleanup action | Selected visible mesh is joined by actual material identity in one undoable operation | Pass with Alpha.4.0.1 ring-light asset: 74 inputs to 31 material meshes |
| Root pinning | Closed/expanded-member selection is rejected; one open group head selected through its pink box is accepted | Pass with Alpha.4.0.1 pink-box instruction and pinned-root workflow |
| Shape detection | Counts Shape/Spline/Line-class descendants without inspecting spline topology and classifies zero-polygon geometry as linework | Pass with Alpha.4.0.1 ring-light asset: 141 detected Shapes |
| Shape deletion refusal | Stops before the main cleanup confirmation and reports the detected Shape count | Automated pass; Max UI pending |
| Shape deletion approval | Deletes approved Shapes in the same cleanup undo transaction | Pass with Alpha.4.0.1 ring-light asset: 141 Shapes deleted |
| Identical duplicate material detection | Same-name Physical/V-Ray materials with matching recursive fingerprints are eligible for merge | Pass with Alpha.4.1.0 ring-light asset: five identical sets detected |
| Different material setup protection | Same name with different class, properties, or nested maps remains separate | Automated pass; differing ring-light materials remained separate |
| Duplicate material approval/refusal | Approval creates one `<name>_MERGED` copy; refusal preserves separate material identities | Approval pass with Alpha.4.1.0: ten originals replaced; refusal automated pass |
| Update action | **Install Update from ZIP...** opens the Python ZIP updater | Pass |
| In-session update reload | The next menu action loads the replaced Python files instead of Max's cached modules | Automated pass; Max host retest pending |
| Project action | **Project Page** opens the BlendMax repository | Pass |
| About action | **About BlendMax** displays installed version information | Pass |
| Menu-to-package workflow | Alpha.3.2 menu export produces a valid `.blendmax` ZIP with FBX, manifest, and textures | Pass |

## Production asset baseline

| Asset | Geometry and materials | Packaged resources | Result |
| --- | --- | --- | --- |
| `Basketbalv2l.blendmax` | One Editable Mesh; 2,276 vertices; 4,548 triangles; UVs, normals, tangents, binormals, and two polygon material IDs; one Multi/Sub parent with two `VRayMtl` children | Two 1500 x 1500 JPEG maps; standard `Bitmaptexture` diffuse and `Normal_Bump` -> `Bitmaptexture` bump graph | Pass with Alpha.3.5; exact manifest bounds match decoded FBX within 0.000000224 m and zero warnings |
| `4pottedplants.blendmax` | One root group with four nested plant groups and 12 geometry nodes; 168,980 vertices; 174,837 polygons; Multi/Sub -> three `VRay2SidedMtl` leaf branches -> front/back `VRayMtl`, plus direct pot, substrate, and branch materials | Eight unique PNG files represented by 13 graph-owned bitmap references; three `VRayColor` nodes and one procedural `Noise` node | Pass with Alpha.3.5; hierarchy, UVs, polygon material IDs, graph ownership, and exact bounds retained with zero warnings |
| Ring-light SKP-derived Max asset | 74 input meshes, nested groups, 31 material identities before duplicate comparison, and extensive imported linework | Five identical material sets merged; ten originals replaced; 141 Shapes deleted | Pass with Alpha.4.1.0: 26 clean material meshes retained under the root |

## Exporter regression checks

| Check | Automated result | 3ds Max result |
| --- | --- | --- |
| Reflection Roughness map disabled, multiplier 37% | Pass | Pass with `TestBox(4).blendmax` |
| Relative bitmap path links graph node/property to packaged texture | Pass | Pass with `TestBox_TEST5.blendmax`; `maps\\RELATIVE.png` resolved from the scene folder and was packaged with its graph ownership intact |
| Duplicate bitmap filenames receive distinct package paths | Pass | Pass with `TestBox_TEST3_R02.blendmax`; two different `FAN.png` files produced distinct content hashes, `FAN.png` and `FAN_7d446767.png`, with correct slot ownership |
| Disconnected/stale global bitmap is not packaged | Pass by graph-only collection | Pass with `TestBox_TEST4.blendmax`; only the connected `CONNECTED.png` was packaged |
| Multi/Sub material IDs and sub-material graph are retained | Pass by graph serialization and FBX material export | Pass with `Test6.blendmax`; FBX polygon material IDs and both assigned textures were retained with zero warnings |
| Grouped geometry excludes a light/helper from object records | Pass | Pass with `TestBox_TEST2_R01.blendmax`; FBX contains only the group root and two meshes |
| Closed group temporarily opens and restores its original state | Pass | Export passed; final Max UI state confirmation pending |
| FBX selection contains geometry payload only, not the group head | Pass | Pass; FBX retained the renamed group root only as the required ancestor and excluded its ignored siblings |
| Unexpected Max selection expansion aborts before FBX export | Pass | Pending |
| Geometry below an ignored helper is reparented to the exported group | Pass | Pending |
| Existing FBX settings restored after success | Pass | Pending |
| Existing FBX settings restored after export failure | Pass | Pending |
| Shape nodes excluded from the v0.1 geometry contract | Pass | Pending |
| Rotated geometry uses exact evaluated world-space bounds | Pass | Pass with `Basketbalv2l.blendmax`; maximum manifest-to-FBX dimension delta was 0.000000224 m |
| Failed evaluated-mesh bounds clean up and fall back to node bounds | Pass | Runtime failure path covered automatically |
| Grouped asset accepts 30 geometry nodes and rejects 31 | Pass | Existing 12-geometry production asset passes; exact 30/31 Max boundary test pending |
| Hidden/frozen scene object aborts export before FBX processing | Pass | Pending |
| Hidden/frozen scene object aborts cleanup before geometry processing | Pass | Pending |
| Cleanup removes all nested groups but retains the selected root | Pass by planner | Pending |
| Multi/Sub faces resolve through explicit `materialIDList`, not list position | Pass | Pending |
| Face-material scan crosses the Python/Max boundary once per staging mesh | Pass by implementation review | Pending performance test |

## Automated regression suite

Alpha.4.1.0 passes 92 automated tests across the Max exporter/cleanup and Blender
importer, including:

- one-object and one-group scene rules;
- the inclusive 30-object group limit and 31-object rejection boundary;
- tiny and oversized asset policies;
- evaluated world-space mesh bounds, temporary mesh cleanup, and safe fallback;
- material graph serialization and parameter pruning;
- duplicate-name Physical/V-Ray material fingerprints, nested-map differences,
  merge approval/refusal, and multi-variant naming;
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
- 3ds Max 2025 manifest component categories;
- isolated `python.ExecuteFile` launcher imports;
- strict hidden/frozen-object preflight for cleanup and export;
- explicit open-group pink-box root pinning;
- root-scoped Shape detection and refusal-before-cleanup behavior;
- zero-polygon geometry classification as imported linework;
- root-scoped cleanup planning and nested-group preservation;
- explicit Multi/Sub material-ID lookup and compact BitArray generation; and
- the Cleanup submenu/action launcher in the installable AppBundle.

Run the suite from the project root:

```bash
python -m unittest discover -s tests -v
```

## Importer contract tracking

The Blender importer now consumes these exporter fields:

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

No exporter freeze is currently planned. Compound material graphs are captured
by the exporter; additional Blender shader translations remain incremental.
