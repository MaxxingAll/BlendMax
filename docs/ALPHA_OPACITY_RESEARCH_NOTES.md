# Alpha/Opacity Research Notes

## 3ds Max

3ds Max Standard material types expose opacity and opacity-map state through the material/map API, including an enabled opacity map path. This means opacity detection can be based on actual material state rather than a material-name heuristic.

## V-Ray

Chaos V-Ray documents an opacity-map workflow for leaf cutouts. The opacity map determines which portions of the leaf surface are visible, making the geometry visually dependent on that map.

## BlendMax implication

Join Mesh by Material can stage and split Multi/Sub geometry before joining material buckets. For alpha/opacity assets, the safest Skip behavior is therefore to detect the assigned material graph first and exclude the entire source geometry node before staging/splitting.

For Multi/Sub materials, whole-node protection is intentional: if any nested material/map path is alpha/opacity-sensitive, the complete source node is skipped. No face-level analysis is required for this PR.

References:

- Autodesk 3ds Max MAXScript Material API: opacity / opacity-map properties.
- Autodesk 3ds Max MAXScript Multi/Sub-Object material API.
- Chaos V-Ray documentation: opacity-map leaf workflow.
