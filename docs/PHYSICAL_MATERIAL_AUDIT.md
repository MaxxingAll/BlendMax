# Physical Material Compatibility Audit

This document records the first audit of BlendMax's existing `PhysicalMaterial` translator against the documented 3ds Max Physical Material model. It is intentionally separate from the translator implementation so verified limitations can be addressed incrementally.

## Reference

The audit uses Autodesk's 3ds Max Physical Material documentation as the behavioral reference:

- Physical Material Parameters: https://help.autodesk.com/cloudhelp/2025/ENU/3DSMax-Lighting-Shading/files/GUID-C1328905-7783-4917-AB86-FC3CC19E8972.htm
- Basic Parameters Rollout: https://help.autodesk.com/cloudhelp/2025/ENU/3DSMax-Lighting-Shading/files/GUID-B8A945E2-3C37-4A7A-90FA-D7209BE59643.htm
- Coating Parameters Rollout: https://help.autodesk.com/cloudhelp/2025/ENU/3DSMax-Lighting-Shading/files/GUID-F8DE5D0C-0A76-4018-AE80-6CFEE34302AF.htm

## Audit status

| Physical Material area | Current BlendMax handling | Classification | Next action |
| --- | --- | --- | --- |
| Base Color / Weight | Principled Base Color / Base Weight | Supported | Keep |
| Roughness + Inv | Principled Roughness with inversion | Supported | Keep |
| Metalness | Principled Metallic | Supported | Keep |
| IOR | Principled IOR | Supported | Keep |
| Reflection Weight | Principled Specular IOR Level approximation | Approximation | Validate perceptual/physical equivalence |
| Reflection Color | Principled Specular Tint approximation | Approximation | Validate, especially metallic edge tint |
| Transparency Weight | Principled Transmission Weight | Supported approximation | Validate against Max glass/frosted cases |
| Transparency Color | Mixed into Base Color; map path currently overrides Base Color | Approximation / limitation | Rework transmission-color handling without destroying base color |
| Transparency Roughness | Not translated independently | Unsupported | Add explicit mapping/approximation |
| Transparency Inv | Not translated independently | Unsupported | Add with transparency roughness |
| Transparency Depth | Not translated | Unsupported | Determine best Blender volume/absorption approximation |
| Thin-Walled | Principled Thin Wall | Supported approximation | Validate solid vs shell behavior |
| SSS Weight | Principled Subsurface Weight | Partial | Add color/depth/scale/scatter handling |
| SSS Color | Not translated | Unsupported | Map where Blender permits |
| SSS Scatter Color | Not translated | Unsupported | Determine approximation |
| SSS Depth | Not translated | Unsupported | Determine scale/radius approximation |
| SSS Scale | Not translated | Unsupported | Determine scale mapping |
| Emission Weight / Color / Luminance | Principled emission color + strength | Partial | Validate unit/scaling behavior |
| Emission Kelvin | Not translated | Unsupported | Add temperature-to-RGB conversion if source data is available |
| Anisotropy / Rotation | Principled anisotropy controls | Supported approximation | Validate rotation convention |
| Coating Weight / Color / Roughness / IOR | Principled Coat controls | Supported approximation | Validate coat color and IOR behavior |
| Coating Affect Underlying Color | Not translated | Unsupported | Add layered approximation if justified |
| Coating Affect Underlying Roughness | Not translated | Unsupported | Add layered approximation if justified |
| Coating Bump | Not translated | Unsupported | Add dedicated coat-normal path |
| Advanced Reflectance Custom Curve | Not translated | Unsupported | Keep explicit compatibility gap unless a principled equivalent is established |

## Important findings

### 1. The translator is already substantially functional

The current implementation covers the primary PBR controls: base color/weight, roughness, metalness, IOR, transmission weight, thin-wall behavior, coat controls, sheen, subsurface weight, emission, anisotropy, and several texture slots.

### 2. Transparency is not a simple color-to-transmission mapping

3ds Max distinguishes transparency weight, transparency color, transparency roughness, inversion, depth, and thin-walled behavior. The current Blender target exposes transmission weight but does not provide a one-to-one transmission-color input in the same model. The current implementation therefore mixes the transparency color into the base color and uses the same base-color socket for a transparency-color map. This should be treated as an explicit approximation rather than a complete translation.

### 3. Subsurface is currently only a weight-level translation

The source material exposes SSS/translucency color, scatter color, depth, and scale in addition to weight. The current implementation only transfers the weight. These parameters should not be silently considered supported.

### 4. Advanced reflectance must remain explicit

Autodesk documents both IOR-driven Fresnel reflectance and an optional custom reflectance curve. The existing translator does not reproduce a custom curve. This is a legitimate compatibility gap and should be reported once the serialized exporter parameter names are verified.

### 5. Coating has behavior beyond Blender's simple Coat controls

3ds Max supports Affect Underlying Color, Affect Underlying Roughness, and a dedicated coating bump map. The current implementation handles the primary coat controls but not these secondary effects.

## Scope of this audit PR

This PR records the verified audit and does **not** change material translation behavior. The next fidelity PR should implement the highest-value corrections, add regression coverage for each correction, and only then populate `PhysicalMaterial` entries in `material_compatibility.py` using the exact serialized parameter names observed in BlendMax manifests.

That last requirement is deliberate: documentation labels such as `Transparency Depth` must not be guessed into registry keys. Registry entries should correspond to actual exported parameter names confirmed by fixtures or real `.blendmax` manifests.
