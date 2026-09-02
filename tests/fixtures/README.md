# Headless material fixtures

These JSON files are **simulated BlendMax manifests**. They stand in for the
material payload captured from 3ds Max/V-Ray so importer integration tests can
run with ordinary Python and without launching 3ds Max, V-Ray, or Blender.

They are not evidence that a V-Ray host produced these exact values. Real host
exports remain the ground truth for renderer-specific behavior. When a real
export reveals a casing or parameter-shape difference, add or update a fixture
and keep the regression test.

All fixtures use the real `.blendmax` manifest contract (`schema.version` in
the 0.1.x family, currently 0.1.1 in these captures). The Blender importer
release version is separate and is not embedded as `schema.version`.

Current coverage:

- `vraymtl_basic.json`: case-insensitive parameter capture and basic Principled
  defaults.
- `vraymtl_surface.json`: anisotropy, sheen, thin film, coat tint, diffuse
  roughness, thin-wall refraction, and refraction-glossiness divergence.
- `vraymtl_maps.json`: VRayMtl bitmap graph links plus Diffuse, Reflection,
  Reflection roughness, Refraction, and Bump map controls, including enable
  state, multiplier clamping, packaged texture records, and slot normalization.

The intended test path is:

`simulated Max/V-Ray manifest -> parse_manifest -> ManifestIndex -> material graph helpers/MaterialBuilder -> fake bpy node tree`
