# BlendMax Max Exporter v0.1 alpha.3

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
- A grouped asset may contain at most 15 geometry/shape nodes.
- Geometry outside the single asset group causes an error.
- Cameras, lights, and other non-geometry nodes are ignored and reported.
- Assets smaller than 1 cm on their largest dimension are rejected with the
  roast notification.
- Assets wider or deeper than 50 m are exported at their original size, but the
  manifest records the scale Blender must apply to fit the 50 x 50 m limit.
- FBX is exported in binary form, Z-up, metres, without animation or embedded
  textures.

## Material status

This alpha records assigned material classes, conversion-relevant material/map
parameters, sub-material connections, sub-texture connections, and discoverable
bitmap paths. V-Ray colours are serialized as RGBA values from 0 to 1. Only map
controls for connected texture slots are retained, reducing manifest noise.

Alpha.3 preserves separate Fresnel and refraction IOR values and the explicit
Fresnel-IOR lock state. Verified `VRayMtl` coverage currently includes Diffuse,
Reflection Roughness, Bump, Metalness, Fresnel IOR, Refraction, and Opacity maps.

## Verified environment

The exporter has been tested in Autodesk 3ds Max 2025.3 with V-Ray 7.00.02.
V-Ray release families from 7.00.x through 7.40.x are treated as compatible.

Full V-Ray-to-Blender material interpretation is **not claimed complete**.
Advanced compound materials such as `VRayBlendMtl` remain deferred.

## Local tests

From the extracted project folder, using ordinary Python:

```bash
python -m unittest discover -s tests -v
```

The tests cover scene rules, size policy, texture collection, archive creation,
AppBundle construction, installation, and ZIP update safety. Actual `pymxs`,
FBX, and 3ds Max menu behavior must be tested inside 3ds Max.
