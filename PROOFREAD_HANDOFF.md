# BlendMax — Changes & Facts Handoff (for proofreading)

Purpose: a single self-contained document for a second AI (or human) to audit
everything changed in the `arena/01a05c3d-blendmax` session, verify the facts
each change relies on, and spot mistakes. It lists the exact files, the new
behavior, the source-backed facts, the *inferences* that carry risk, and how to
reproduce the results. **§9 records the previous review round and how each
point was addressed.**

---

## 0. Working state

- Branch: `arena/01a05c3d-blendmax` (off `main` @ `b8572c5`).
- Four commits ahead of `main`, all pushed:
  1. `619006c` — "Harden VRayMtl import and map anisotropy, sheen, thin film, coat"
  2. `3659464` — "Tighten parameter canonicalization after review"
  3. `cbe49d4` — "Lock the VRayMtl parameter-name contract and refresh handoff"
  4. this commit — bump importer 0.1.4 → 0.1.5 + host-check procedures
- **Blender importer version bumped 0.1.4 → 0.1.5** in
  `blendmax_blender/__init__.py` (string + `bl_info`), and
  `blendmax_blender/blender_manifest.toml`. The build tool names the ZIP from
  the manifest version, so it will produce `blendmax_importer-0.1.5.zip`.
- Tests: **124 passing** (started at 99).
- No `max_adapter.py` / exporter-side changes. All changes are on the Blender
  importer side + its tests + docs.

Reproduce: `python -m unittest discover -s tests` (ordinary Python, no Blender
or 3ds Max needed).

---

## 1. File-by-file change inventory

### `blendmax_blender/material_graph.py` (pure logic, no `bpy`)

Added:

1. `parameter_key(value)` — normalizes a material *parameter* name by
   casefold only (`str(value).strip().casefold()`), preserving punctuation.
2. `_PARAMETER_ALIASES: Dict[str, str]` — explicit alias table (alias →
   canonical, both normalized). Currently empty by design; the escape hatch
   for cross-release spellings.
3. `class ParameterView(MappingABC)` — case-insensitive, access-recording view
   keyed on `parameter_key`, with explicit-alias fallback.
4. `vray_anisotropy(parameters) -> (magnitude, rotation)`
5. `vray_sheen_roughness(parameters) -> float`
6. `vray_thin_film(parameters) -> (ior, thickness_nm)`

`canonical_name()` is unchanged and still used for **slot/class** matching
(where punctuation-insensitivity is intentional). Its docstring now spells out
the split: slots/classes use `canonical_name`, parameters use `parameter_key`.

### `blendmax_blender/blender_materials.py` (node-building, uses `bpy`)

1. Imports: added `ParameterView`, `vray_anisotropy`, `vray_sheen_roughness`,
   `vray_thin_film`.
2. Wrapped the parameters dict in `ParameterView(...)` in five places:
   `_build_physical_mtl`, `_build_vray_mtl`, `_texture_output` (the
   `vraycolor` and `noise` branches), `_normal_output` (the `normalbump`
   branch).
3. `_build_vray_mtl` gained new `_set_default` mappings (see §3) plus a
   refraction-glossiness divergence warning block.
4. `_build_vray_mtl` gained an end-of-function diagnostic loop that warns about
   every parameter key never read (skipping `texmap`-prefixed keys).

### `tests/fakes.py` (NEW)

Extracted from `test_blender_physical_material.py`: `FakeSocket`, `FakeSockets`,
`FakeNode`, `FakeNodes`, `FakeLinks`, `FakeTree`, and `load_materials_module()`.

### `tests/test_blender_physical_material.py`

Refactored to import fakes from `fakes.py`. Test logic unchanged.

### `tests/test_blender_vray_material.py` (NEW)

9 tests for the VRayMtl builder (see §7).

### `tests/test_blender_material_graph.py`

Added `ParameterViewTests` (8 tests) and 6 pure-helper tests for the new
`vray_*` functions.

### Docs

- `README.md`, `BLENDER_IMPORTER_TEST_MATRIX.md`, `CHANGELOG.md` updated.

---

## 2. New behavior (what the importer now does differently)

### 2a. Case-insensitive parameter resolution (spelling-preserving)

Every parameter lookup goes through `ParameterView`, keyed on
`parameter_key(key)` = casefold only. So `Diffuse`, `DIFFUSE`, `diffuse` all
resolve; but `reflection glossiness` does **not** resolve to
`reflection_glossiness` (spaces/underscores are not collapsed). Known
cross-release spellings must be listed in `_PARAMETER_ALIASES` explicitly.

Rationale (from review round 1): punctuation-stripping universal
canonicalization could silently collapse two distinct property names; the
stricter spelling-sensitive key plus an explicit alias table removes that
hazard.

### 2b. Unmapped-parameter diagnostics (VRayMtl only)

At the end of `_build_vray_mtl`, every normalized key in the manifest that was
never read produces:

> `VRayMtl parameter '<key>' has no Blender mapping yet; its value remains in the stored manifest.`

- `texmap_*` keys are skipped (map controls, already interpreted).
- Deduplicated via the existing `_warn` set.
- Only VRayMtl, not Physical Material (exporter captures Physical unfiltered;
  flagging it would flood the verified Ring-Light pass).

### 2c. New VRayMtl mappings

| V-Ray param (whitelist name) | → Blender Principled input | Rule |
|---|---|---|
| `anisotropy` | `Anisotropic` | `abs(value)` clamped 0..1 |
| `anisotropy_rotation` | `Anisotropic Rotation` | pass-through 0..1; **+0.25 if `anisotropy < 0`**, wrapped mod 1 |
| `sheen_color` | `Sheen Weight` | `luminance(sheen_color)` |
| `sheen_color` | `Sheen Tint` | pass-through rgba |
| `sheen_glossiness` | `Sheen Roughness` | `1 - glossiness` clamped 0..1 |
| `thinfilm_ior` | `Thin Film IOR` | `max(1.0, value)` |
| `thinfilm_thickness_min` | `Thin Film Thickness` | min if `thinfilm_on` else 0 |
| `thinfilm_thickness_max` | (read only) | NOT used; read to suppress the unmapped diagnostic |
| `coat_color` | `Coat Tint` | pass-through rgba |
| `diffuse_roughness` | `Diffuse Roughness` | pass-through 0..1 |
| `refraction_thinwalled` | `Thin Wall` | bool |

### 2d. Refraction-glossiness divergence warning

If a material is transmissive (`luminance(refraction) > 0`) and
`refraction_glossiness` differs from `reflection_glossiness` after both are
converted to roughness (> 0.0001 delta):

> `{name} has separate reflection and refraction glossiness values; Blender's Principled shader uses a single roughness for both, so the refraction roughness is approximated.`

Blender's Principled has one `Roughness` for both reflection and transmission,
so only the reflection roughness is applied and the divergence is reported.

---

## 3. Facts the changes rely on (with sources)

| # | Fact | Source | Confidence |
|---|---|---|---|
| F1 | V-Ray `anisotropy` range is −1..1; 0 = isotropic | Chaos App SDK: "anisotropy … from -1 to 1 (0.0 is isotropic reflections)" — https://documentation.chaos.com/space/APPSDK/132811653/V-Ray+Material | HIGH |
| F2 | V-Ray `anisotropy_rotation` range is 0.0–1.0 (one full turn) | same Chaos App SDK page: "anisotropy_rotation – The rotation of the anisotropy axes, from 0.0 to 1.0" | HIGH |
| F3 | Blender `Anisotropic` is 0..1 magnitude; `Anisotropic Rotation` is 0..1 = "1.0 going full circle" | Blender source `node_shader_bsdf_principled.cc` (both sockets `PROP_FACTOR`, min 0 max 1; rotation description "with 1.0 going full circle") — https://raw.githubusercontent.com/blender/blender/main/source/blender/nodes/shader/nodes/node_shader_bsdf_principled.cc | HIGH |
| F4 | Blender negative anisotropy = "highlights shaped along the tangent direction" (sign = axis flip) | Blender Principled docs (Anisotropic socket description); confirmed by Stack Exchange answer | HIGH |
| F5 | V-Ray `sheen_color` doubles as the sheen amount in 3ds Max; default is **black** (= sheen off) | Jamie Cardoso reference: "Sheen color … determines the color of the sheen … The default color is black" — https://jamiecardoso-mentalray.blogspot.com/2022/05/vray-material-library-textures.html | HIGH for default-black; MEDIUM for "luminance = amount" (see I1) |
| F6 | V-Ray `sheen_glossiness` default 0.8; glossiness 1 = sharp → roughness = 1 − glossiness | Jamie Cardoso reference (same page): "Default value 0.8"; "Lower values yield a more diffused shine" | HIGH |
| F7 | V-Ray thin-film thickness is nanometers; **min/max collapses to min when no blend map**; disabled = off | Chaos docs (Cinema 4D / SketchUp): "Thickness Min (nm) … If no Thickness Blend is applied, only this value is used"; thickness blend map blends min↔max — https://docs.chaos.com/display/VC4D/V-Ray+Material+Node and https://documentation.chaos.com/space/VSKETCHUP/109802909/Generic+Thin+Film | HIGH |
| F8 | Blender `Thin Film Thickness` is in nanometers, `PROP_WAVELENGTH`, min 0 max 100000; 0 = off | Blender source `node_shader_bsdf_principled.cc` (same file) | HIGH |
| F9 | V-Ray `coat_color` "tints all layers — reflection, sheen, diffuse and refraction"; default white | Chaos VRayMtl Coat docs — https://docs.chaos.com/display/VMAYA/VRayMtl+Coat ; default white from Jamie Cardoso reference | HIGH |
| F10 | V-Ray `coat_darkening` is a clear-coat absorption/darkening effect with no Blender equivalent | Chaos VRayMtl Coat docs (same page): "emulates how a clear coat layer slightly darkens the underlying material due to light absorption and scattering" | HIGH |
| F11 | V-Ray `diffuse_roughness` is a 0..1 surface-roughness parameter; Blender `Diffuse Roughness` is 0..1 with 0 = Lambertian | Blender socket description: "0.0 is perfect lambertian reflection, 1.0 is completely rough" (source file above); V-Ray name/range from repo `VRAY_MTL_PROPERTIES` + general V-Ray docs | HIGH |
| F12 | `refraction_thinwalled` (thin-shell glass) ≈ Blender `Thin Wall` | Repo `VRAY_MTL_PROPERTIES` lists `refraction_thinwalled`; V-Ray "thin-walled" refraction means same surface on both sides — matches Blender Thin Wall description | MEDIUM (name from repo whitelist, semantics by analogy) |
| F13 | V-Ray refraction glossiness **stays glossiness** even when "Use roughness" is enabled (unlike reflection) | TurboSquid transmission guide: "when enabling Use roughness, Refraction Glossiness does not switch to its roughness counterpart … we need to invert the roughness map and apply it to the Refraction Glossiness" — https://resources.turbosquid.com/transmission-tips-max-vray/ | HIGH |
| F14 | Blender Principled has a **single** Roughness for reflection and transmission (no separate transmission roughness socket) | Blender source file: only one `Roughness` socket is declared in the node | HIGH |

`luminance()` = 0.2126·R + 0.7152·G + 0.0722·B (Rec.709) — pre-existing helper,
reused (not newly introduced).

---

## 4. Inferences / judgment calls — highest review priority

**I1 — Sheen Weight = `luminance(sheen_color)`.**
V-Ray 3ds Max has no separate sheen *amount*; intensity comes from the sheen
color. I used Rec.709 luminance as the weight and passed the color through as
tint. Risks: (a) V-Ray's internal mapping of sheen-color brightness to sheen
intensity may not be linear luminance; (b) Blender's Sheen Weight applies to a
fixed tint, so setting both weight and tint from the same color could
double-apply the darkening. **Requires a 3-material host A/B** (white sheen,
saturated sheen, equal-luminance variant). Maya's VRayMtl has a separate Sheen
"Amount" (Chaos VMAYA docs) — worth double-checking 3ds Max truly lacks it.

**I2 — Negative `anisotropy` → +0.25 (90°) rotation.**
V-Ray's negative sign flips the elongation axis (perpendicular). Blender only
has a non-negative magnitude plus a rotation, so I encode the flip as a quarter
turn. The exact ±90° convention was **not** verified against a render.
**Requires a brushed-metal host A/B** to confirm the rotation direction.

**I3 — Thin-film "on" flag is `thinfilm_on`.**
Name taken from the repo's own `VRAY_MTL_PROPERTIES` whitelist, not
independently verified against Chaos MaxScript docs. Low risk (only
`thinfilm_*` enable-style property in the whitelist), but worth a 30-second
confirm.

**I4 — Unmapped diagnostics fire for VRayMtl only.**
Physical Material capture is unfiltered on the exporter side, so flagging
Physical would flood the verified Ring-Light "no warnings" pass. Deliberate
scope decision; extend the diagnostic if Physical capture is ever filtered.

**I5 — `thinfilm_thickness_max` is read-but-ignored.**
It only applies with a thickness-blend map, which isn't wired. Reading it keeps
it out of the unmapped diagnostics. The code comment now explicitly states this
(see §9). If a blend map is ever wired, this helper must start consuming `max`.

**I6 — `canonical_name` collisions (RESOLVED in round 1).**
Previously `ParameterView` keyed on punctuation-stripping `canonical_name`,
which could collapse distinct names. Now keyed on `parameter_key` (casefold
only, spelling preserved), so collisions require two names that differ only by
case — which is the intended equivalence. `canonical_name` remains only for
slot/class matching, where collisions are benign and fuzziness is desired.

**I7 — Refraction divergence threshold 0.0001.**
Matches the pre-existing IOR-lock tolerance. Cosmetic, but consistent.

---

## 5. Suggested verification checklist for the reviewing AI

1. Re-read `blendmax_blender/material_graph.py` and
   `blendmax_blender/blender_materials.py` diffs for logic errors (esp. the
   `ParameterView._resolve` alias fallback, the refraction-glossiness
   comparison, and the `unmapped_keys` loop).
2. Confirm each fact in §3 against its source URL (especially F12, F13).
3. Confirm the property *names* used in the new mappings exist in the repo's
   `VRAY_MTL_PROPERTIES` whitelist in `blendmax_max/max_adapter.py`.
4. Sanity-check `ParameterView`: `get` records access only on hit (direct or
   alias); `__getitem__` records then raises on miss; `__contains__` does not
   record; `unmapped_keys()` is sorted(keys − accessed); alias is single-hop.
5. Confirm no Physical-Material path emits the new unmapped warning (the loop
   exists only in `_build_vray_mtl`).
6. Confirm `_PARAMETER_ALIASES` is empty and unused in production (the alias
   path is only exercised by tests) — or, if populated, that every entry maps
   to a real stored key.
7. Run `python -m unittest discover -s tests` (expect 122 OK) and
   `python -m unittest tests.test_blender_vray_material -v` (expect 9 OK).
8. Confirm doc counts are consistent: README "122 tests", matrix
   "Fifty-two importer-specific tests".

---

## 6. Deliberately NOT done (context for the reviewer)

- **No exporter-side changes.** `VRAY_MTL_PROPERTIES` still captures
  renderer-internal properties (`option_*`, `reflection_dimdistance_*`,
  `refraction_fog*`, `*_maxdepth`, `*_affectalpha`, `selfillumination_gi`,
  `anisotropy_axis`/`_channel`/`_derivation`, `brdf_type`). These now surface
  as unmapped warnings — by design, for a later "exclude from capture" pass.
- **No `refraction_dispersion` → Transmission Dispersion** (needs a V-Ray
  Abbe-number scale check against Blender's 9–91 clamp).
- **No `translucency_*` → Subsurface** (deferred per the roadmap's
  "specialized materials later").
- **No new material classes** (VRayLightMtl / VRayBlendMtl / VRayOverrideMtl
  are still next-up roadmap items).
- **No version bump.**
- **Host verification pending** in Blender 5.2 with a real `VRayMtl` asset
  (anisotropy/sheen A/B cases are the explicit blockers — see §9).

---

## 7. Exact test inventory after all changes

| File | Tests |
|---|---|
| tests/test_blender_adapter_placement.py | 4 |
| tests/test_blender_extension_build.py | 2 |
| tests/test_blender_manifest.py | 4 |
| tests/test_blender_material_graph.py | 21 |
| tests/test_blender_package.py | 4 |
| tests/test_blender_physical_material.py | 3 |
| tests/test_blender_placement.py | 5 |
| tests/test_blender_vray_material.py | 11 |
| **Importer-specific subtotal** | **54** |
| **Full suite (discover -s tests)** | **124** |

---

## 8. Open blockers before merge

These are host checks that cannot run in the automated sandbox — they require
3ds Max + V-Ray + Blender 5.2. The exact recipes requested by the PR review
are reproduced here and in `BLENDER_IMPORTER_TEST_MATRIX.md`.

1. **Host A/B: negative anisotropy sign.** Brushed-metal `VRayMtl`, two
   variants — A: `anisotropy = +0.5`, `rotation = 0.0`; B:
   `anisotropy = -0.5`, `rotation = 0.0`. Export both, import into Blender,
   compare highlight direction. Confirms the importer's `+0.25` (90°) mapping
   matches V-Ray visually.
2. **Host A/B: sheen.** Three `VRayMtl`s — A: white sheen; B: saturated red
   sheen; C: different color with ~same luminance as A. Confirms
   `luminance(sheen_color) → Sheen Weight` + `sheen_color → Sheen Tint` and
   checks for double-encoding of intensity.
3. **Live Max parameter-casing confirmation.** Export one real `VRayMtl`,
   inspect `manifest.json`, confirm `getPropNames` keys (casefolded) for
   `reflection_glossiness`, `refraction_glossiness`, `brdf_useRoughness`,
   `selfIllumination` match the whitelist spellings. This is the empirical
   confirmation behind the static contract tests in §10.
4. (Optional) Confirm `thinfilm_on` and `refraction_thinwalled` property names
   against Chaos MaxScript docs (F12 / I3, MEDIUM confidence).

---

## 9. Review round 1 → responses

The previous review found the work "good and worth keeping" but flagged four
items. Responses, all applied in the follow-up commit:

1. **"`canonical_name` is more aggressive than case-insensitive."**
   → FIXED. Added `parameter_key` (casefold only) for parameter lookups,
   preserved punctuation, and added an explicit `_PARAMETER_ALIASES` table as
   the escape hatch. `ParameterView` no longer strips punctuation. Tests were
   updated to assert both that punctuation variants are rejected and that
   explicit aliases resolve. (See §2a, I6.)
2. **"Anisotropy sign conversion needs a real render test."**
   → Agreed; cannot be settled without a host. Added the A/B case to
   `BLENDER_IMPORTER_TEST_MATRIX.md` "Pending host validation", the README
   "Material status" caveat, the CHANGELOG "Host evidence", and §8 here. Left
   the code as-is (arithmetic is unit-tested; direction is the open question).
3. **"Sheen luminance derivation should not merge blindly."**
   → Same treatment as #2: documented as an unsettled inference with the exact
   3-material A/B to run, in all three docs + §8.
4. **"Thin-film max thickness looks like it was handled."**
   → FIXED. `vray_thin_film` docstring and inline comment now explicitly state
   the limitation ("Supported when no thickness-blend map exists", "max is
   intentionally NOT used"), and it is listed under "Known Alpha.1 limits" in
   the test matrix.

"Unmapped-parameter diagnostics stay" and "no Max exporter change needed" were
both affirmed by the reviewer; no action taken.

---

## 10. Review round 2 → responses

The second review accepted the code direction and flagged two items. Both are
addressed in this commit:

1. **"The alias table is empty — verify the actual Max-exported parameter
   names against the current lookup names."**
   → Verified statically and locked in with regression tests. The exporter can
   only store VRayMtl properties listed in `VRAY_MTL_PROPERTIES` (plus
   `texmap_*` map controls for connected slots), so the importer's vocabulary
   was extracted from source (`ast`-based) and diffed against that whitelist.
   Result: 27 of 28 literal lookups casefold-match a whitelist name; the 28th
   (`texmap_bump_multiplier`) is a map control, which the exporter emits
   separately. The reviewer's five names all resolve:
     - `reflection_glossiness` → whitelist `reflection_glossiness` ✓
     - `reflectionGlossiness` → not a *property* name; the property is
       `reflection_glossiness` (snake). The camel spelling appears only inside
       `texmap_reflectionGlossiness_*` map-control keys, matching the
       exporter's `_MAP_CONTROL_NAMES`. No alias needed. ✓
     - `refraction_glossiness` → ✓
     - `brdf_useRoughness` → casefold-matches `brdf_useroughness` ✓
     - `selfIllumination` → casefold-matches `selfillumination` ✓
   Two permanent tests now encode this: `test_every_vray_parameter_lookup_is_
   exporter_reachable` (ast-extracts the importer's lookups and asserts each is
   whitelist- or `texmap_`-reachable, with a non-empty sanity guard) and
   `test_full_whitelist_reads_expected_parameters` (feeds all 65 whitelist
   names and asserts the mapped set is consumed and the unmapped set is
   reported). A future exporter or importer name change that breaks the
   contract fails these tests.
   Residual host step: one real `VRayMtl` export to confirm `getPropNames`
   casing equals the whitelist spelling (the whitelist is the best available
   proxy; it is presumed to reflect real MaxScript property names).

2. **"The handoff document is slightly stale."**
   → FIXED in this commit. §0 now lists all three commits (with the third
   described as "this commit" to avoid re-staling), and §10 (this section)
   records the round-2 state. Test counts updated to 124 / 54.

---

## 11. Review round 3 → responses (PR #2 comment)

The PR owner posted on PR #2 ("Host validation before merge"). It requests
three host checks and a version bump. Responses:

1. **Three host checks** — negative-anisotropy A/B, sheen A/B, and live
   parameter-casing confirmation. These require 3ds Max + V-Ray + Blender 5.2
   and therefore cannot be executed in the automated sandbox. They are queued
   for the host side; the exact recipes are recorded in
   `BLENDER_IMPORTER_TEST_MATRIX.md` ("Pending host validation") and §8 above
   so they are reproducible and their results (with screenshots) can be posted
   to the PR.
2. **Version bump 0.1.4 → 0.1.5** — DONE in this commit, in
   `blendmax_blender/__init__.py` (string and `bl_info`) and
   `blendmax_blender/blender_manifest.toml`; the build tool derives the ZIP
   name from the manifest version, so it now emits `blendmax_importer-0.1.5.zip`.
   README status/install references and the test-matrix title were updated;
   `tests/test_blender_extension_build.py` version assertion updated to 0.1.5.
   Historical 0.1.4 mentions (e.g. the Ring-Light pass) were left intact as
   release history.

PR #2 stays open until the three host checks pass and results are recorded.
