# BlendMax Max Exporter v0.1 alpha.3.4

BlendMax packages one isolated 3ds Max asset for conversion in Blender. The Max
side is written in Python with `pymxs` and creates:

```text
AssetName.blendmax
├── geometry.fbx
├── manifest.json
└── textures/
```

`geometry.fbx` carries geometry and scene structure. `manifest.json` is data
created automatically by Python.

## Target environment

- Autodesk 3ds Max 2025.3
- Python 3.11 supplied with 3ds Max
- V-Ray 7.00.x through 7.40.x

Other modern Max versions and V-Ray releases outside that range receive a
compatibility warning rather than a hard rejection. Patch builds within each
supported V-Ray release family are accepted.

## Install the persistent 3ds Max menu

1. Extract the release ZIP.
2. In 3ds Max, choose **Scripting > Run Script** one final time.
3. Select `install_blendmax.py`.
4. Restart 3ds Max.
5. Use **BlendMax > Export Asset...** from the main menu.

The installer places `BlendMax.bundle` in the current Windows user's Autodesk
ApplicationPlugins folder. It does not modify the 3ds Max installation folder
and does not require administrator rights.

3ds Max 2025 introduced a new menu system. Its menu actions still require a
small MacroScript/MAXScript registration bridge; all exporter, installer,
updater, validation, and material logic remains Python.

## Update BlendMax

1. Download a newer BlendMax release ZIP without extracting it.
2. In 3ds Max, choose **BlendMax > Install Update from ZIP...**.
3. Select the ZIP and restart 3ds Max when prompted.

The updater validates the release structure, rejects unsafe archive paths,
builds a new AppBundle in a staging directory, and replaces only the installed
`BlendMax.bundle` folder. If installation fails, the previous bundle is
restored.

`run_blendmax_max.py` remains available as a development fallback.

## v0.1 rules

- The scene must contain exactly one grouped asset or one standalone object.
- A grouped asset may contain at most 15 geometry nodes.
- Geometry outside the single asset group causes an error.
- Shapes, cameras, lights, helpers, and other non-geometry nodes are ignored
  and reported. Convert required splines to geometry before exporting.
- Assets smaller than 1 cm on their largest dimension are rejected with the
  roast notification.
- Assets wider or deeper than 50 m are exported at their original size, but the
  manifest records the scale Blender must apply to fit the 50 x 50 m limit.
- FBX is exported in binary form, Z-up, metres, without animation or embedded
  textures. BlendMax restores the user's previous FBX exporter settings when
  the export finishes or fails.

## Material status

This alpha records assigned material classes, conversion-relevant material/map
parameters, sub-material connections, sub-texture connections, and reachable
bitmap paths. V-Ray colours are serialized as RGBA values from 0 to 1. Only map
controls for connected texture slots are retained, reducing manifest noise.
Each packaged texture record explicitly identifies its material-graph node,
source parameter, raw Max path, resolved source path, and package path. This
keeps relative paths and duplicate filenames unambiguous for the Blender
importer.

Alpha.3 preserves separate Fresnel and refraction IOR values and the explicit
Fresnel-IOR lock state. Verified `VRayMtl` coverage currently includes Diffuse,
Reflection Roughness, Bump, Metalness, Fresnel IOR, Refraction, and Opacity maps.

Alpha.3.1 corrects the 3ds Max 2025 AppBundle component categories used to load
the persistent menu and its post-start-up registration script.

Alpha.3.2 makes every menu launcher add its installed Python directory before
importing `blendmax_actions`, matching how 3ds Max runs files with
`python.ExecuteFile`.

Alpha.3.3 preserves the
Reflection Roughness map's V-Ray `reflectionGlossiness` enable/multiplier
controls, copies only graph-reachable textures, excludes ignored scene nodes
from object records, restores FBX settings, and formalizes geometry-only v0.1
support. The manifest schema is `0.1.1`.

Alpha.3.4 fixes closed-group selection discovered during the mixed-group test.
BlendMax temporarily opens asset groups before selecting the intended group
geometry payload, restores their original open/closed state afterward, and
aborts if 3ds Max adds any unexpected nodes to the FBX selection. The group
head remains represented in the manifest without forcing FBX to recurse through
every group member.

## Verified environment

The exporter has been tested in Autodesk 3ds Max 2025.3 with V-Ray 7.00.02.
V-Ray release families from 7.00.x through 7.40.x are treated as compatible.

The **Max exporter is under active development**. The Blender importer is
deliberately deferred while exporter behavior, scene coverage, and material
coverage continue to improve. The persistent menu and the nine core `VRayMtl`
features are verified, while every new exporter change receives automated and
3ds Max regression testing. See the
[`TEST_MATRIX.md`](https://github.com/MaxxingAll/BlendMax/blob/main/TEST_MATRIX.md)
record for the complete manual and automated results.

Full V-Ray-to-Blender material interpretation is **not claimed complete**.
Advanced compound materials such as `VRayBlendMtl` remain deferred.

## Local tests

From the extracted project folder, using ordinary Python:

```bash
python -m unittest discover -s tests -v
```

The 35 tests cover scene rules, size policy, texture ownership and collisions,
group isolation and restoration, archive creation, FBX state restoration,
AppBundle construction, installation, and ZIP update safety. Actual `pymxs`,
FBX, and 3ds Max menu behavior must be tested inside 3ds Max.
