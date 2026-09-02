# BlendMax — Changes & Facts Handoff (for proofreading)

Purpose: a single self-contained document for a second AI (or human) to audit everything changed in the `arena/01a05c3d-blendmax` session, verify the facts each change relies on, and spot mistakes. This document is also the current status handoff for PR #2.

---

## 0. Current working state

- Branch: `arena/01a05c3d-blendmax`.
- PR: **#2**, `Harden VRayMtl import: case-insensitive params, unmapped diagnostics, anisotropy/sheen/thin-film/coat`.
- PR #2 is **OPEN, not merged**.
- Current PR head: `22cfabca5df1b4d4a2447d9f5bfd30b1eee3fc3b`.
- Main/base: `main` @ `b8572c5`.
- Blender importer version: **0.1.5**.
- The real-host validation gate for anisotropy, sheen, and live Max parameter casing has been completed successfully.
- **Current merge blocker:** perform one clean Blender re-import after the latest warning/note UI changes, verify the expected unsupported fields are emitted as grouped notes rather than warnings, then run/confirm the repository CI checks.
- **Do not merge PR #2 yet.**

The branch history includes the exporter 500-object-limit test update and the latest importer warning/note cleanup commits. The latest note-related design is intentionally conservative: known unsupported V-Ray properties are informational notes; unknown/unexpected properties remain warnings.

Reproduce unit tests with: `python -m unittest discover -s tests` (ordinary Python; no Blender or 3ds Max required).

---

## 1. File-by-file change inventory

### `blendmax_blender/material_graph.py`

Added/changed:

1. `parameter_key(value)` — normalizes material parameter names by `casefold()` only, preserving punctuation.
2. `_PARAMETER_ALIASES` — explicit alias table for future cross-release spellings; currently empty by design.
3. `ParameterView` — case-insensitive parameter view with access tracking and explicit-alias fallback.
4. `vray_anisotropy(parameters)`.
5. `vray_sheen_roughness(parameters)`.
6. `vray_thin_film(parameters)`.
7. `unmapped_keys()` reports normalized parameter keys that were present but never accessed by the importer mapping path.

`canonical_name()` remains for slot/class matching, where punctuation-insensitive matching is intentional. It is not used as the parameter key normalizer.

### `blendmax_blender/blender_materials.py`

- VRayMtl parameters are accessed through `ParameterView`.
- Added VRayMtl → Principled mappings for anisotropy, sheen, thin film, coat tint, diffuse roughness, and thin-walled refraction.
- Added separate reflection/refraction glossiness divergence detection.
- Added a known-unsupported V-Ray property set so intentionally unsupported fields are not treated as runtime warnings.
- **Known unsupported properties are accumulated into the importer `notes` channel instead of being emitted one-by-one as warnings.**
- Truly unexpected/unrecognized VRayMtl properties still use the existing warning text:
  `VRayMtl parameter '<key>' has no Blender mapping yet; its value remains in the stored manifest.`
- Divergent refraction glossiness material names are accumulated and reported once as a grouped note instead of producing one repeated warning per material.

### `blendmax_blender/models.py`

`ImportSummary` now contains:

- `warnings: Tuple[str, ...]`
- `notes: Tuple[str, ...]`

This separates actual problems from known/expected importer limitations.

### `blendmax_blender/blender_adapter.py`

- Import still starts warnings from manifest warnings.
- The material builder receives the separate notes collection so expected unsupported parameters do not increase the warning count.
- Final import summary carries both warning and note collections.

### `blendmax_blender/addon.py`

The operator continues to report warnings through Blender's warning channel and prints warning messages. The expected-limitation note path is separate and should not be presented as a warning.

### `blendmax_max/validation.py`

`DEFAULT_MAX_OBJECTS = 500`.

### `tests/test_validation.py`

Boundary coverage was updated to accept 500 payload objects and reject 501.

### `tests/test_blender_vray_material.py`

Covers VRayMtl mapping, case-insensitive lookup, unmapped parameter diagnostics, anisotropy/sheen/thin-film behavior, glossiness divergence, texture controls, and importer/exporter parameter vocabulary contract.

The latest warning/note behavior should also be covered by tests for:

- known unsupported fields becoming notes, grouped once;
- unexpected fields remaining warnings;
- multiple materials with divergent glossiness producing one grouped note containing the material names;
- mapped fields producing neither a warning nor a note.

### Docs

`README.md`, `BLENDER_IMPORTER_TEST_MATRIX.md`, `CHANGELOG.md`, and this handoff are being updated to reflect the current 0.1.5 state and the warning/note distinction.

---

## 2. Current importer behavior

### 2a. Case-insensitive parameter resolution

`Diffuse`, `DIFFUSE`, and `diffuse` resolve to the same stored parameter. Punctuation is preserved, so `reflection glossiness` is not silently treated as `reflection_glossiness`. Future spelling variations should be added explicitly to `_PARAMETER_ALIASES`.

### 2b. Known unsupported V-Ray parameters are NOTES, not WARNINGS

The importer knows about a set of V-Ray properties that are intentionally captured/preserved but do not currently have a direct Principled BSDF mapping. These are expected limitations for this release.

They should be grouped into **one note**, conceptually:

> `(anisotropy_axis/anisotropy_channel/.../translucency_thickness) is not supported yet, wait for future BlendMax updates`

The actual field list is generated from the known unsupported set and sorted for deterministic output.

The important behavior is:

- do **not** emit one warning per known unsupported field;
- do **not** count known unsupported fields as warnings;
- preserve their original values in the stored manifest;
- report them together as a future-support note.

The current known unsupported group includes the fields observed in the real `geometry.fbx` import such as:

`anisotropy_axis`, `anisotropy_channel`, `anisotropy_derivation`, `brdf_type`, `coat_darkening`, `option_cutoff`, `option_doublesided`, `option_glossyfresnel`, `option_opacitymode`, `option_openpbrmode`, `option_tracediffuse`, `option_tracereflection`, `option_tracerefraction`, `reflection_affectalpha`, `reflection_dimdistance`, `reflection_dimdistance_falloff`, `reflection_dimdistance_on`, `reflection_fresnel`, `reflection_maxdepth`, `refraction_affectalpha`, `refraction_affectshadows`, `refraction_dispersion`, `refraction_dispersion_on`, `refraction_fogbias`, `refraction_fogcolor`, `refraction_fogdepth`, `refraction_fogmult`, `refraction_fogunitsscale_on`, `refraction_maxdepth`, `selfillumination_gi`, `translucency_amount`, `translucency_color`, `translucency_fbcoeff`, `translucency_multiplier`, `translucency_on`, `translucency_scattercoeff`, `translucency_surfacelighting`, `translucency_thickness`.

This list is an implementation decision for the current release, not a statement that these parameters can never be mapped. They remain in the manifest so later BlendMax updates can use them.

### 2c. Unexpected/unrecognized VRayMtl parameters remain WARNINGS

A newly captured parameter that is not mapped and is not on the known unsupported list still produces:

> `VRayMtl parameter '<key>' has no Blender mapping yet; its value remains in the stored manifest.`

This preserves forward-compatibility diagnostics. The purpose of the warning is now specifically to catch something BlendMax did **not** already classify as an expected gap.

### 2d. Refraction-glossiness divergence is a single grouped NOTE

Blender Principled exposes one roughness value for reflection and transmission. When a transmissive material has meaningfully different reflection and refraction glossiness values, the importer keeps the reflection roughness as the Principled roughness and records the divergence.

Instead of one message per material, the importer should emit one grouped note such as:

> `(Mat3d66-493277-5-556/Mat3d66-493277-3-789/Mat3d66-493277-2-158) has separate reflection and refraction glossiness values; Blender's Principled shader uses a single roughness for both, so the refraction roughness is approximated.`

This is informational because the approximation is known and intentional, not an import failure.

### 2e. Missing packaged texture remains a WARNING

A message like:

> `Packaged image for texture graph node tex_2140 is unavailable.`

is still a real warning because the referenced asset data is unavailable to the importer. This should **not** be converted into a note.

---

## 3. Real-host verification completed

### 3a. Negative anisotropy — PASS

A real V-Ray material with `anisotropy = -0.5` was exported and imported.

Verified in Blender:

- Anisotropic = `0.5`
- Anisotropic Rotation = `0.25`

For this milestone, acceptance is correct BSDF data adaptation. V-Ray-vs-Blender renderer visual parity is not the acceptance criterion.

### 3b. Sheen — PASS

Three real-host materials were checked:

- white sheen → Weight `1.000`, white tint;
- saturated red sheen → Weight `0.213`, red tint;
- green sheen `(0, 0.297, 0)` → Weight `0.212`, green tint.

This validates the current luminance → Sheen Weight and original color → Sheen Tint adaptation.

### 3c. Live Max parameter casing — PASS

A live VRayMtl was inspected via MaxScript and Python `pymxs`. The following parameter names were observed/read successfully:

- `#reflection_glossiness`
- `#refraction_glossiness`
- `#brdf_useRoughness`
- `#selfIllumination`

---

## 4. V-Ray → Blender mapping table

| V-Ray param | Blender Principled | Rule |
|---|---|---|
| `anisotropy` | `Anisotropic` | absolute magnitude, clamped 0..1 |
| `anisotropy_rotation` | `Anisotropic Rotation` | 0..1 rotation; negative anisotropy adds 0.25 turn, wrapped |
| `sheen_color` | `Sheen Weight` | Rec.709 luminance |
| `sheen_color` | `Sheen Tint` | original rgba |
| `sheen_glossiness` | `Sheen Roughness` | `1 - glossiness` |
| `thinfilm_ior` | `Thin Film IOR` | minimum 1.0 |
| `thinfilm_thickness_min` | `Thin Film Thickness` | minimum thickness when enabled |
| `thinfilm_thickness_max` | read only | ignored until thickness blend mapping exists |
| `coat_color` | `Coat Tint` | pass-through rgba |
| `diffuse_roughness` | `Diffuse Roughness` | 0..1 |
| `refraction_thinwalled` | `Thin Wall` | bool |

---

## 5. Facts and confidence

The earlier fact table remains applicable, including:

- V-Ray anisotropy supports negative-to-positive values and a 0..1 rotation range.
- Blender Principled anisotropy magnitude/rotation sockets are 0..1.
- V-Ray sheen color is used as the source of sheen appearance; current BlendMax uses luminance for the Blender weight and the original color for tint.
- V-Ray thin-film thickness is represented in nanometers and uses min thickness when no blend map is active.
- Blender Principled exposes a single roughness value for reflection/transmission, hence the current refraction-glossiness approximation.

The sheen-weight conversion and negative-anisotropy quarter-turn remain implementation decisions backed by the completed host tests, not claims of exact renderer visual equivalence.

---

## 6. High-priority review items for the next AI

1. Confirm that known unsupported V-Ray fields are accumulated into `notes`, not `warnings`.
2. Confirm the grouped unsupported note is emitted once, with deterministic field ordering, and retains the exact future-update wording:
   `(field/field/field ...) is not supported yet, wait for future BlendMax updates`
3. Confirm divergent reflection/refraction glossiness emits one grouped note containing all affected material names, not one note per material.
4. Confirm truly unknown VRayMtl parameters still produce the existing warning.
5. Confirm missing packaged textures and other genuine data-loss conditions remain warnings.
6. Confirm mapped parameters remain silent.
7. Run `python -m unittest discover -s tests` and verify the count/result against the current repository rather than relying on stale handoff numbers.
8. Re-import `geometry.fbx` in clean Blender 5.2 with the current 0.1.5 importer and record the exact console output.
9. Confirm the PR checks on the latest head before merge.
10. Do not merge while the clean Blender re-import has not been confirmed.

---

## 7. Deliberately NOT done

- No exporter-side removal of known unsupported fields. They remain in the manifest for future support.
- No `refraction_dispersion` → Blender dispersion mapping yet.
- No `translucency_*` → Subsurface mapping yet.
- No new material classes beyond the current supported scope.
- No exact V-Ray/Blender renderer parity claim.
- No merge of PR #2 yet.

---

## 8. Current expected `geometry.fbx` result

Given the previously observed import output, the next clean import should **not** produce the long sequence of individual `BlendMax warning: VRayMtl parameter ...` messages for the known unsupported fields.

Expected remaining messages from that same asset are:

1. One **note** grouping the known unsupported fields.
2. One **note** grouping the three materials with separate reflection/refraction glossiness values.
3. The missing packaged-image message as a genuine **warning** if `tex_2140` is still unavailable.

The exact material names and field list depend on the imported manifest, so a reviewer should use the actual clean-import output as the final evidence.

---

## 9. Previous review round / host-validation record

The previous review requested real-host checks for negative anisotropy, sheen, and live parameter casing. All three were completed and recorded in PR #2. The acceptance criterion for this milestone is correct parameter capture/adaptation rather than renderer visual parity.

The next review round is specifically about **diagnostic quality**: expected limitations should read as notes, true problems should remain warnings, and repeated per-material/per-field noise should be consolidated.

---

## 10. PR status handoff

PR #2 is **not ready to merge yet**.

Current intended sequence:

`code changes → clean Blender re-import → verify notes/warnings → CI/checks → final review → merge`

The key status for another AI taking over is: **feature implementation and real-host validation are done; diagnostic cleanup is implemented; the remaining task is to verify the actual Blender runtime output and final checks.**
