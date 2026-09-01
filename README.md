# BlendMax v0.1

BlendMax transfers one isolated 3ds Max asset into Blender. The Max exporter
and Blender importer are Python-first, modular, and designed so compatibility
changes stay inside small application adapters.

The Max exporter creates:

```text
AssetName.blendmax
├── geometry.fbx
├── manifest.json
└── textures/
```

`geometry.fbx` carries geometry and scene structure. `manifest.json` is data
created automatically by Python.

## Current status

| Component | Version | Status |
| --- | --- | --- |
| 3ds Max exporter and cleanup | `0.1.0-alpha.4.1.0` | Host verified in 3ds Max 2025.3 |
| Blender importer | `0.1.4` | Ring-Light Physical Material pass completed in Blender 5.2 |
| `.blendmax` manifest | `0.1.1` | Current exporter/importer contract |
| Automated suite | 119 tests | Passing |

See [CHANGELOG.md](CHANGELOG.md) for release history,
[TEST_MATRIX.md](TEST_MATRIX.md) for Max evidence, and
[BLENDER_IMPORTER_TEST_MATRIX.md](BLENDER_IMPORTER_TEST_MATRIX.md) for Blender
coverage.

## Target environment

- Max exporter: Autodesk 3ds Max 2025.3, its supplied Python 3.11, and V-Ray
  7.00.x through 7.40.x.
- Blender importer: Blender 5.2 is the primary tested target. Blender 4.2 or newer
  is accepted, with no maximum-version lock.

Other modern Max versions and V-Ray releases outside that range receive a
compatibility warning rather than a hard rejection. Patch builds within each
supported V-Ray release family are accepted.

The Blender adapter feature-detects Blender's current and legacy FBX operators
and shader socket/property names. This does not promise that a future Blender
API can never break compatibility, but it keeps any required fix isolated from
the package, manifest, and material-graph code.

## Install the persistent 3ds Max menu

1. Extract the release ZIP.
2. In 3ds Max, choose **Scripting > Run Script** one final time.
3. Select `install_blendmax.py`.
4. Restart 3ds Max.
5. Use **BlendMax > Export Asset...** from the main menu.

The **BlendMax > Cleanup > Join Mesh by Material...** command is an explicit
pre-export tool for hierarchy-heavy assets such as imported SketchUp models.
Open the asset group and select its pink group-head box to pin that group as the
cleanup root. Closed or expanded-member selections are intentionally rejected
with this instruction.

The installer places `BlendMax.bundle` in the current Windows user's Autodesk
ApplicationPlugins folder. It does not modify the 3ds Max installation folder
and does not require administrator rights.

3ds Max 2025 introduced a new menu system. Its menu actions still require a
small MacroScript/MAXScript registration bridge; all exporter, installer,
updater, validation, and material logic remains Python.

## Join Mesh by Material cleanup

The cleanup command works on copies first, splits Multi/Sub faces using the
explicit material ID list, joins pieces that reference the same actual material
object, and places the results under the selected root. Nineteen referenced
materials therefore produce nineteen output geometry objects even when the
source contains many nested mesh nodes.

When separate materials share a normalized name, cleanup fingerprints only
that duplicate-name set. Physical Material fingerprints include every readable
public value plus the complete recursive sub-material and texture-map graph;
V-Ray fingerprints include conversion-relevant values, map controls, and the
same recursive topology. Names, Max handles, Slate positions, and preview state
do not affect equality. BlendMax offers to merge only structurally identical
sets into a copied `<name>_MERGED` material. Refusing keeps the original
material identities and separate output meshes. Same-name materials with
different setups are never silently combined.

Safety rules are deliberately simple:

- if any scene object is hidden-in-viewport or frozen, cleanup stops before
  touching geometry and asks the user to make every object visible and
  unfrozen;
- Shape/Spline/Line-class nodes inside the selected root are counted without
  inspecting their spline topology; zero-polygon geometry is also classified
  as imported linework. BlendMax asks whether to delete all of it before
  showing the normal cleanup confirmation;
- refusing Shape deletion stops cleanup and reports the detected count, while
  approving it deletes those nodes inside the same undoable transaction;
- approved identical-material sets are reassigned to one copied material before
  geometry bucketing, while differing or unreadable setups remain separate;
- all nested groups are removed one level at a time after their source meshes
  have been replaced;
- the selected root is always retained;
- source geometry is deleted only after every material output has been built;
  and
- the confirmed operation is recorded as one 3ds Max undo step.

The command never runs automatically during export. The normal result is the
root group plus one mesh per material.

## Update BlendMax

1. Download a newer BlendMax release ZIP without extracting it.
2. In 3ds Max, choose **BlendMax > Install Update from ZIP...**.
3. Select the ZIP. The updated Python core is loaded by the next BlendMax
   action; restart 3ds Max only when a release changes the menu layout.

The updater validates the release structure, rejects unsafe archive paths,
builds a new AppBundle in a staging directory, and replaces only the installed
`BlendMax.bundle` folder. If installation fails, the previous bundle is
restored. Each menu launcher invalidates Max's embedded-Python module cache so
an updated exporter or cleanup action cannot continue running stale code.

`run_blendmax_max.py` remains available as a development fallback.

## Install the Blender importer

Build or download `blendmax_importer-0.1.4.zip`, then in Blender:

1. Open **Edit > Preferences > Get Extensions**.
2. Open the menu in the top-right and choose **Install from Disk**.
3. Select the importer ZIP and enable **BlendMax Importer** if needed.
4. Use **File > Import > BlendMax Asset (.blendmax)**.

Installing a newer version of the same extension ZIP updates the isolated
extension. There are no background services, handlers, or polling loops.

To build the ZIP from source:

```bash
python tools/build_blender_extension.py
```

## Blender import behavior

The importer validates archive paths before extracting, reads only the declared
manifest/FBX/textures, calls Blender's FBX importer once, and then rebuilds the
asset from indexed manifest data. A failed import removes the objects and data
created by that attempt.

It currently:

- restores original object names and manifest parent relationships;
- removes FBX-created objects that have no manifest record, including synthetic
  scene-root geometry/helpers;
- places the asset in its own collection under one `[BlendMax]` controller;
- directly centers imported FBX geometry at world origin, grounds its lowest
  point at Z=0, and keeps reconstructed group pivots close to their own meshes;
- preserves FBX polygon material indices and reconstructs Multi/Sub slots;
- converts `VRayMtl` and 3ds Max `PhysicalMaterial` to native Principled BSDF
  nodes;
- recursively handles `VRay2SidedMtl`, `Bitmaptexture`, `VRayBitmap`,
  `Normal_Bump`, `VRayColor`, and basic `Noise`;
- maps V-Ray Diffuse, Reflection, Roughness/Glossiness, Metalness, Fresnel IOR,
  Refraction, Opacity, Self-Illumination, Anisotropy (magnitude and rotation),
  Sheen (color-derived weight, glossiness, tint), Thin Film (IOR and thickness),
  Coat (amount, glossiness, IOR, tint), Diffuse Roughness, thin-walled
  refraction, Bump, and tangent normal maps;
- maps Physical Material base color/weight, reflectivity, roughness inversion,
  metalness, transparency, IOR, thin-wall state, emission, coat, sheen,
  anisotropy, SSS weight, thin film, bump, cutout, and their supported maps;
- honors exported map enable states and multipliers;
- resolves manifest parameter names case-insensitively, so V-Ray/Max casing
  or spelling variations cannot silently fall back to defaults; and
- packs loaded images into Blender so temporary extraction files can be
  deleted safely.

The complete original `manifest.json` is also stored as a Blender Text data
block and referenced by the asset collection/controller. Parameters that do not
yet have a native Blender equivalent therefore remain available for later
converter improvements instead of being discarded. During a `VRayMtl` import,
any manifest parameter the importer does not map to a Blender shader input is
reported as a warning (once per parameter name), so untested aliases and
parameters surface instead of being silently ignored.

Unsupported graph classes receive a visible magenta fallback and a warning
instead of aborting the whole asset.

## v0.1 rules

- The scene must contain exactly one grouped asset or one standalone object.
- A grouped asset may contain at most 30 geometry nodes. Nested group heads and
  ignored non-geometry nodes do not count toward this limit.
- Geometry outside the single asset group causes an error.
- Hidden-in-viewport or frozen scene objects stop export with a clear preflight
  error. BlendMax never silently skips them.
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

Verified `VRayMtl` coverage currently includes Diffuse, Reflection Roughness,
Bump/Normal, Metalness, Fresnel IOR, Refraction, Opacity, Self-Illumination,
Anisotropy, Sheen, Coat, Diffuse Roughness, thin-walled refraction, and Thin
Film. V-Ray anisotropy is stored as -1..1 (the sign flips the elongation axis)
and `anisotropy_rotation` as 0..1 for one full turn; the importer maps the
magnitude to Blender's Anisotropic input and adds a quarter turn for negative
values, matching Blender's 0..1 full-circle Anisotropic Rotation. Sheen color
doubles as the sheen amount in V-Ray, so its luminance drives Blender's Sheen
Weight and its glossiness is inverted to Sheen Roughness. V-Ray thin-film
thickness is a min/max range that collapses to the minimum when no
thickness-blend map is connected, matching V-Ray's own behavior; a disabled
thin film maps to zero thickness. Coat color maps to Coat Tint; V-Ray's
separate coat-darkening effect has no Blender equivalent and remains flagged.
Blender's Principled shader uses one roughness for reflection and refraction,
so a V-Ray material whose refraction glossiness diverges from its reflection
glossiness is imported using the reflection roughness and reported as an
approximation. Release-by-release material and workflow changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## Verified environment

The exporter has been tested in Autodesk 3ds Max 2025.3 with V-Ray 7.00.02.
V-Ray release families from 7.00.x through 7.40.x are treated as compatible.

Max exporter Alpha.4.1.0 passed the ring-light cleanup workflow: 74 input
meshes became 26 material meshes, five identical material sets replaced ten
original assignments, and 141 Shape/segment objects were deleted. The
Alpha.3.6 export baseline, persistent menu, and nine core `VRayMtl` features
remain verified. Blender importer 0.1.2 completed its Basketball and
four-potted-plants material, hierarchy, and world-origin placement passes.
Importer 0.1.4 completed the Ring-Light Blender 5.2 pass with 26 objects and 26
native materials, no warnings or errors, both packaged base-color images wired,
and the hierarchy and world-origin placement intact. The undeclared `Untitled`
FBX object exposed by 0.1.3 is removed together with its orphaned geometry.

Full V-Ray-to-Blender material interpretation is **not claimed complete**.
Advanced compound materials such as `VRayBlendMtl` remain deferred.

## Local tests

From the extracted project folder, using ordinary Python:

```bash
python -m unittest discover -s tests -v
```

The 119 tests cover scene and visibility-preflight rules, cleanup planning,
Multi/Sub ID lookup, compact face selections, the 30-object boundary, exact and fallback
bounds, size policy, texture ownership and collisions,
group isolation and restoration, archive creation, FBX state restoration,
AppBundle construction, installation, hot-reloading after an in-session ZIP
update, ZIP update safety, duplicate-name material fingerprints, Physical
Material property and nested-map comparison, merge approval/refusal, Blender manifest
parsing, secure extraction, V-Ray and Physical Material interpretation, legacy schema fallback,
origin placement, nested-group anchoring, reproducible extension packaging,
case-insensitive parameter resolution, unmapped-VRayMtl-parameter diagnostics,
and V-Ray anisotropy, sheen, thin-film, coat, diffuse-roughness, thin-walled
refraction, and refraction-glossiness interpretation.
Actual `pymxs`, `bpy`, FBX, and host UI
behavior must be tested inside 3ds Max and Blender.
