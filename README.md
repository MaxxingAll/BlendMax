# BlendMax

BlendMax packages one isolated Autodesk 3ds Max asset for conversion in Blender.

`geometry.fbx` carries geometry and scene structure. `manifest.json` is data
created automatically by Python.

## Current status

| Component | Version | Status |
| --- | --- | --- |
| 3ds Max exporter and cleanup | `0.1.0-alpha.4.3.0` | Host verified in 3ds Max 2025.3 |
| Blender importer | `0.1.7` | Structured import summary after successful import |
| `.blendmax` manifest | `0.1.1` | Current exporter/importer contract |
| Automated suite | See CI | Python 3.11–3.13 |

See [CHANGELOG.md](CHANGELOG.md) for release history,
[TEST_MATRIX.md](TEST_MATRIX.md) for Max evidence, and
[BLENDER_IMPORTER_TEST_MATRIX.md](BLENDER_IMPORTER_TEST_MATRIX.md) for Blender
coverage.

## Target environment

- Max exporter: Autodesk 3ds Max 2025.3, its supplied Python 3.11, and V-Ray
  7.00.x–7.40.x.
- Blender importer: Blender 4.2 or newer; host-tested baseline uses Blender 5.2.

## Blender import diagnostics

After a successful `.blendmax` import, BlendMax opens a compact **BlendMax Import Complete** dialog with the asset name and counts for imported objects, materials, packaged textures, warnings, and compatibility notes. Known limitations are grouped under **Compatibility Notes**, while actionable problems remain under **Warnings**.

The existing console messages are retained, so the popup is a user-facing summary rather than a replacement for debugging output. Clean imports explicitly show that no warnings or compatibility notes were generated.
