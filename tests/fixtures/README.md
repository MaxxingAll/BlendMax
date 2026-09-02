# Headless material fixtures

These JSON files are **simulated BlendMax manifests**. They stand in for the
material payload captured from 3ds Max/V-Ray so importer integration tests can
run with ordinary Python and without launching 3ds Max, V-Ray, or Blender.

They are not evidence that a V-Ray host produced these exact values. Real host
exports remain the ground truth for renderer-specific behavior. When a real
export reveals a casing or parameter-shape difference, add or update a fixture
and keep the regression test.

Current coverage:

- `vraymtl_basic.json`: case-insensitive parameter capture and basic Principled
  defaults.
- `vraymtl_surface.json`: anisotropy, sheen, thin film, coat tint, diffuse
  roughness, thin-wall refraction, and refraction-glossiness divergence.

The intended test path is:

`simulated Max/V-Ray manifest -> parse_manifest -> ManifestIndex -> MaterialBuilder -> fake bpy node tree`
