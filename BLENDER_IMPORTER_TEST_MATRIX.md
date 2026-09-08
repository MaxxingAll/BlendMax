# BlendMax Blender Importer 0.1.8 Test Matrix

## Scope

Primary tested target: Blender 5.2. Minimum declared version: Blender 4.2.0. No
maximum Blender version is declared; API variation is contained in the Blender
adapter through operator, socket, and property feature detection.

The importer does not run a background service, persistent handler, or polling
loop. The 0.1.8 developer workflow adds one-shot use of `bpy.app.timers` only to
defer the **Reload BlendMax** operation until the current Preferences operator
has returned.

Reload operates on the currently installed extension copy. It does not watch
the repository working tree or continuously execute in the background.

## Automated status

GitHub Actions runs the ordinary Python test suite on Python 3.11, 3.12, and
3.13. The suite covers Blender packaging/manifest behavior, importer
translation, V-Ray parameter and map contracts, diagnostics grouping, Max
cleanup/export validation, installer / update paths, and restart/hot-reload
state handling. The exact suite count is intentionally taken from the latest
CI run rather than maintained as a static number here.

The headless V-Ray fixtures are deliberately simulated manifests, not claims
that a running V-Ray host produced those exact values. They provide a fast
regression layer for the importer pipeline; real Max/V-Ray A/B tests remain the
ground truth for renderer-specific host behavior.

## Hot-reload manual verification

### A. Legacy add-on layout — PENDING HOST TEST

1. Install BlendMax using the legacy add-on layout.
2. Open **Edit > Preferences > Add-ons** and enable BlendMax.
3. Confirm the **Reload BlendMax** button is visible in BlendMax Preferences.
4. Make a controlled change in the installed copy, such as a diagnostic string.
5. Click **Reload BlendMax** once and confirm the add-on remains enabled.
6. Confirm the changed code is active without restarting Blender and that the
   first successful reload consumes the restart notice.
7. Click the button twice rapidly and confirm only one reload is scheduled.
8. Force an import-time error in the installed copy, click Reload, and confirm
   the System Console receives a traceback and the restart notice becomes visible.

### B. Blender extension ZIP layout — PENDING HOST TEST

1. Build `blendmax_importer-0.1.8.zip` and install it through **Install from Disk**.
2. Confirm Blender registers the extension under its `bl_ext.*` package namespace.
3. Open **Edit > Preferences > Extensions > BlendMax Importer** and confirm
   **Reload BlendMax** is available.
4. Make a controlled change in the installed extension copy.
5. Click **Reload BlendMax** and confirm the extension remains enabled and the
   changed code is active without restarting Blender. The first successful
   reload must also remove the restart notice; a second reload must not be
   required merely to consume the notice.
6. Repeat the rapid double-click and import-error checks from the legacy layout.
7. Install a newer BlendMax version into the same Blender process and confirm
   its normal restart notice can appear again before the reload is requested.

Record the exact Blender version, installation layout, build ZIP, and result
here after host validation. The automated suite cannot verify these operator and
extension-loader behaviors because it does not import `bpy`.

## Verified Blender 5.2 manual passes

### A. Basketball

1. Install the importer ZIP from disk.
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
3. Confirm the controller is centered on the asset's world-space bounds center
   and its CUBE display exactly encompasses the imported mesh bounds, the
   plant footprint is centered around X/Y=0, its base rests at Z=0, and
   nested group pivots stay near their own geometry.
4. Confirm the Multi/Sub material retains six leaf/branch slots on its assigned
   meshes.
5. Confirm each leaf `VRay2SidedMtl` becomes a Backfacing-driven front/back
   shader mix.
6. Confirm repeated package images are reused per color-space role and packed.
7. Confirm the procedural pot bump receives a Blender Noise Texture fallback.

### C. Ring-Light Physical Materials

1. Install the importer ZIP and import `RingLight.blendmax` into a clean scene.
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

## Pass criteria

- Import completes without a Python traceback.
- Reload completes without disabling the extension when the installed code is valid.
- Reload never remains queued twice from rapid repeated clicks.
- A successful first reload consumes the pending restart notice; no second reload is required just to clear it.
- Relative object transforms, hierarchy, UVs, normals, tangents, and material
  indices visually match the FBX/export manifest after world-origin placement.
- No unpacked image points at the importer's temporary directory.
- The original manifest is present in Blender's Text data and referenced by the
  asset controller.
- Warnings identify real problems; expected unsupported/approximate V-Ray
  behavior is grouped into informational notes.
- Undo removes the imported asset as one operator action.
