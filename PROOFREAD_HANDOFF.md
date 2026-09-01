# BlendMax — Changes & Facts Handoff (for proofreading)

Purpose: a single self-contained document for a second AI (or human) to audit
everything changed in the `arena/01a05c3d-blendmax` session, verify the facts
each change relies on, and spot mistakes. It lists the exact files, the new
behavior, the source-backed facts, the *inferences* that carry risk, and how to
reproduce the results.

---

## 0. Working state

- Branch: `arena/01a05c3d-blendmax` (off `main` @ `b8572c5`).
- **Nothing committed.** All work is uncommitted changes + two untracked files.
- **Version strings NOT bumped.** `blendmax_blender/__init__.py` and
  `blendmax_blender/blender_manifest.toml` still read `0.1.4`.
- Tests: **119 passing** (started at 99).
- No `max_adapter.py` / exporter-side changes. All changes are on the Blender
  importer side + its tests + docs.

Reproduce: `python -m unittest discover -s tests` (ordinary Python, no Blender
or 3ds Max needed).

---

## 1. File-by-file change inventory

### `blendmax_blender/material_graph.py` (pure logic, no `bpy`)

Added:

1. `class ParameterView(MappingABC)` — a case-insensitive, access-recording
   view over a graph node's `parameters` dict.
2. `vray_anisotropy(parameters) -> (magnitude, rotation)`
3. `vray_sheen_roughness(parameters) -> float`
4. `vray_thin_film(parameters) -> (ior, thickness_nm)`

Imports changed: added `from collections.abc import Mapping as MappingABC`
and `Dict`, `Set` typing imports.

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

### `tests/fakes.py` (NEW, untracked)

Extracted from `test_blender_physical_material.py`: `FakeSocket`, `FakeSockets`,
`FakeNode`, `FakeNodes`, `FakeLinks`, `FakeTree`, and `load_materials_module()`
(imports `blender_materials.py` under a stub `bpy`). `FakeNode.PRINCIPLED_INPUTS`
lists the socket names the fake exposes.

### `tests/test_blender_physical_material.py`

Refactored to import `FakeSocket`, `FakeTree`, `load_materials_module` from
`fakes.py` (with a `sys.path` shim so it also runs as a direct module). Test
logic unchanged.

### `tests/test_blender_vray_material.py` (NEW, untracked)

9 tests for the VRayMtl builder: mixed-casing mapping, unmapped diagnostics
(+ dedup), texmap exclusion, surface-param defaults, thin-film-off behavior,
coat-tint/diffuse-roughness/thin-wall direct mapping, refraction-glossiness
divergence warn + matching no-warn.

### `tests/test_blender_material_graph.py`

Added `ParameterViewTests` (5 tests) and 6 pure-helper tests for the new
`vray_*` functions.

### Docs

- `README.md` — status-table count, bullet lists, "Material status" prose.
- `BLENDER_IMPORTER_TEST_MATRIX.md` — counts + coverage bullets.
- `CHANGELOG.md` — new "Blender Importer (unreleased)" section.

---

## 2. New behavior (what the importer now does differently)

### 2a. Case-insensitive parameter resolution

Every parameter lookup in the material builder now goes through
`ParameterView`, which keys on `canonical_name(key)` =
`re.sub(r"[^a-z0-9]+", "", key.casefold())`.

Effect: `Diffuse`, `DIFFUSE`, `diffuse`, `Reflection-Glossiness`,
`reflectionglossiness` all resolve to the same stored value. This removes the
previous dependence on exact MaxScript property casing (the exporter stores
keys with their original `getPropNames` casing, and the old code did
`parameters.get("Diffuse")` vs `parameters.get("reflection_glossiness")` — a
silent-fallback hazard if a V-Ray patch/locale changed casing).

### 2b. Unmapped-parameter diagnostics (VRayMtl only)

At the end of `_build_vray_mtl`, every canonical key in the manifest that was
never read produces:

> `VRayMtl parameter '<key>' has no Blender mapping yet; its value remains in the stored manifest.`

- `texmap_*` keys are skipped (they are map controls, already interpreted by
  `map_is_enabled`/`map_amount`).
- Deduplicated via the existing `_warn` set (per unique message string).
- Only VRayMtl, **not** Physical Material — the exporter captures Physical
  properties unfiltered, so warning there would flood the verified
  "no warnings" Ring-Light pass with noise. (Judgment call — see §6.)

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
| `thinfilm_thickness_max` | (read only) | touched to keep it out of unmapped diagnostics; not wired |
| `coat_color` | `Coat Tint` | pass-through rgba |
| `diffuse_roughness` | `Diffuse Roughness` | pass-through 0..1 |
| `refraction_thinwalled` | `Thin Wall` | bool |

### 2d. Refraction-glossiness divergence warning

If a material is transmissive (`luminance(refraction) > 0`) and
`refraction_glossiness` differs from `reflection_glossiness` after both are
converted to roughness (> 0.0001 delta):

> `{name} has separate reflection and refraction glossiness values; Blender's Principled shader uses a single roughness for both, so the refraction roughness is approximated.`

Blender's Principled has one `Roughness` for both reflection and transmission,
so only the reflection roughness is applied and the divergence is reported
(same philosophy as the pre-existing separate-IOR warning).

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

These are the places where I made a decision rather than copied a spec. A
proofreader should challenge each:

**I1 — Sheen Weight = `luminance(sheen_color)`.**
V-Ray 3ds Max has no separate sheen *amount*; intensity comes from the sheen
color. I used Rec.709 luminance as the weight and passed the color through as
tint. Risks: (a) V-Ray's internal mapping of sheen-color brightness to sheen
intensity may not be linear luminance (could be max-channel, could be a
sqrt/gamma relationship); (b) Blender's Sheen Weight applies to a fixed tint,
so setting both weight and tint from the same color could double-apply the
darkening. **Recommend a host A/B test: a saturated red sheen vs a white sheen
at same luminance.** Maya's VRayMtl has a separate Sheen "Amount" (Chaos VMAYA
docs) — worth double-checking 3ds Max truly lacks it.

**I2 — Negative `anisotropy` → +0.25 (90°) rotation.**
V-Ray's negative sign flips the elongation axis (perpendicular). Blender only
has a non-negative magnitude plus a rotation, so I encode the flip as a quarter
turn. This is a standard equivalence but the exact ±90° convention (and whether
it should be +0.25 or −0.25) was **not** verified against a render. **Needs a
visual check with a brushed-metal test asset.**

**I3 — Thin-film "on" flag is `thinfilm_on`.**
Name taken from the repo's own `VRAY_MTL_PROPERTIES` whitelist, not
independently verified against Chaos MaxScript docs. Low risk (it's the only
`thinfilm_*` enable-style property in the whitelist), but worth a 30-second
confirm.

**I4 — Unmapped diagnostics fire for VRayMtl only.**
Physical Material capture is unfiltered on the exporter side, so flagging
Physical would flood the verified Ring-Light "no warnings" pass. This is a
deliberate scope decision; if you later add Physical capture filtering, extend
the diagnostic there too.

**I5 — `thinfilm_thickness_max` is read-but-ignored.**
It only applies with a thickness-blend map, which isn't wired. Reading it keeps
it out of the unmapped diagnostics. If a blend map is ever wired, this helper
must start consuming `max` too.

**I6 — `canonical_name` collisions.**
`ParameterView` dedups by canonical key with first-wins `setdefault`. Two
distinct keys that canonicalize identically (e.g. hypothetical `brdf_type` vs
`brdftype`) would silently shadow. Rare for real MaxScript names, but the
proofreader should confirm none of the `VRAY_MTL_PROPERTIES` names collide
after stripping punctuation/case.

**I7 — Refraction divergence threshold 0.0001.**
Matches the pre-existing IOR-lock tolerance. Cosmetic, but consistent.

---

## 5. Suggested verification checklist for the reviewing AI

1. Re-read `blendmax_blender/material_graph.py` and
   `blendmax_blender/blender_materials.py` diffs for logic errors (esp. the
   refraction-glossiness comparison and the `unmapped_keys` loop).
2. Confirm each fact in §3 against its source URL (especially F12, F13).
3. Confirm the property *names* used in the new mappings exist in the repo's
   `VRAY_MTL_PROPERTIES` whitelist in `blendmax_max/max_adapter.py` (they were
   chosen from that list, not retyped).
4. Sanity-check `ParameterView` semantics: `get` records access only on hit;
   `__getitem__` records then raises on miss; `unmapped_keys()` is
   sorted(keys − accessed).
5. Confirm no Physical-Material path emits the new unmapped warning (grep:
   the loop exists only in `_build_vray_mtl`).
6. Confirm the fake `PRINCIPLED_INPUTS` list in `tests/fakes.py` is not
   relied on by production code (it is test-only; production uses
   `_socket`/`_set_default` with canonical-name fallback).
7. Run `python -m unittest discover -s tests` (expect 119 OK) and
   `python -m unittest tests.test_blender_vray_material -v` (expect 9 OK).
8. Confirm the two doc test counts are consistent: README "119 tests",
   matrix "Forty-nine importer-specific tests".

---

## 6. Deliberately NOT done (context for the reviewer)

- **No exporter-side changes.** `VRAY_MTL_PROPERTIES` still captures
  renderer-internal properties (`option_*`, `reflection_dimdistance_*`,
  `refraction_fog*`, `*_maxdepth`, `*_affectalpha`, `selfillumination_gi`,
  `anisotropy_axis`/`_channel`/`_derivation`, `brdf_type`). These will now show
  up as unmapped warnings — by design, to surface them for a later
  "exclude from capture" pass. That pass is future work, not part of this
  change set.
- **No `refraction_dispersion` → Transmission Dispersion** (needs a V-Ray
  Abbe-number scale check against Blender's 9–91 clamp).
- **No `translucency_*` → Subsurface** (deferred per the roadmap's
  "specialized materials later").
- **No new material classes** (VRayLightMtl / VRayBlendMtl / VRayOverrideMtl
  are still next-up roadmap items).
- **No version bump, no commit, no push.**
- **Host verification pending** in Blender 5.2 with a real `VRayMtl` asset
  (anisotropy/sheen/thin-film/coat visuals; warning output). The tests use a
  fake `bpy`, so they validate mapping logic, not render output.

---

## 7. Exact test inventory after all changes

| File | Tests |
|---|---|
| tests/test_blender_adapter_placement.py | 4 |
| tests/test_blender_extension_build.py | 2 |
| tests/test_blender_manifest.py | 4 |
| tests/test_blender_material_graph.py | 18 |
| tests/test_blender_package.py | 4 |
| tests/test_blender_physical_material.py | 3 |
| tests/test_blender_placement.py | 5 |
| tests/test_blender_vray_material.py | 9 |
| **Importer-specific subtotal** | **49** |
| **Full suite (discover -s tests)** | **119** |
