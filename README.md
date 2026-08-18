# BlendMax Max Exporter v0.1 alpha.2

This is the first runnable 3ds Max half of BlendMax. It is written entirely in
Python and uses `pymxs` to create a portable `.blendmax` package containing:

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

## Run it in 3ds Max

1. Extract this project somewhere permanent.
2. Open the asset scene in 3ds Max.
3. Choose **Scripting > Run Script**.
4. Select `run_blendmax_max.py`.
5. Choose where to save the `.blendmax` package.

The exporter temporarily gives nodes unique FBX names and restores their
original names and your previous selection after export.

## v0.1 rules

- The scene must contain exactly one grouped asset or one standalone object.
- A grouped asset may contain at most 15 geometry/shape nodes.
- Geometry outside the single asset group causes an error.
- Cameras, lights, and other non-geometry nodes are ignored and reported.
- Assets smaller than 1 cm on their largest dimension are rejected with the
  roast notification.
- Assets wider or deeper than 50 m are exported at their original size, but the
  manifest records the scale Blender must apply to fit the 50 × 50 m limit.
- FBX is exported in binary form, Z-up, metres, without animation or embedded
  textures.

## Material status

This alpha records assigned material classes, conversion-relevant material/map
parameters, sub-material connections, sub-texture connections, and discoverable
bitmap paths. V-Ray colours are serialized as RGBA values from 0 to 1. Only map
controls for connected texture slots are retained, reducing manifest noise.

Alpha.2 also records detected Max, renderer, and V-Ray versions and ignores
empty `None`/`undefined` bitmap paths. V-Ray release families from 7.00.x
through 7.40.x are treated as compatible. For `VRayMtl`, separate Fresnel and
refraction IOR values and the Fresnel-IOR lock state are preserved.

## Verified Alpha.2 test

The Max exporter has been tested in Autodesk 3ds Max 2025.3 with V-Ray
7.00.02. A `VRayMtl` using separate `VRayBitmap` maps for Diffuse, Bump, and
Reflection Roughness exported all three files with their correct slot names and
no warnings.

Full V-Ray-to-Blender material interpretation is **not claimed complete** in
this build. The current Max-side milestone is to complete core `VRayMtl`
coverage and lock its Blender Principled BSDF mappings. The next major phase is
the Blender `.blendmax` importer. Advanced compound materials such as
`VRayBlendMtl` are deferred until the basic end-to-end conversion works.

## Local tests

From the extracted project folder, using ordinary Python:

```bash
python -m unittest discover -s tests -v
```

The tests cover the scene rules, size policy, texture collection, and archive
creation. Actual `pymxs` and FBX behavior must be tested inside 3ds Max.
