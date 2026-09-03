# Alpha/Opacity Research Notes

## 3ds Max

3ds Max material APIs expose opacity and opacity-map state, including explicit map and enable properties. This supports detection from actual material state rather than material-name heuristics.

Autodesk references:

- Standard material / opacity and opacity-map properties: https://help.autodesk.com/cloudhelp/2025/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57F5EBBA-5F54-4CD4-8993-0B07A3571293.html
- Physical Material / Cutout map properties (`cutout_map` / `cutout_map_on`): https://help.autodesk.com/cloudhelp/2022/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57562F6A-A8A1-4A28-BAE1-0D4729411214.html
- Physical Material Cutout workflow: https://help.autodesk.com/cloudhelp/2020/ENU/3DSMax-Lighting-Shading/files/GUID-65AFACA5-59BD-4731-B384-431E166B2B12.htm
- Multi/Sub-Object material API: https://help.autodesk.com/cloudhelp/2021/ENU/3DSMax-MAXScript/files/GUID-7ECB1E85-6199-4143-BEDA-3B26DD35E0C3.htm

Autodesk documents the Physical Material `cutout_map` and `cutout_map_on` properties, and describes Cutout as a transparency mechanism suitable for foliage on a flat plane.

## V-Ray

Chaos documents an opacity-map workflow for leaf cutouts where the opacity map determines which portions of a leaf surface are visible.

Chaos reference:

- V-Ray for 3ds Max — How to Make Leaves: https://docs.chaos.com/display/VMAX/How%2Bto%2BMake%2BLeaves

The detector intentionally recognizes V-Ray's explicit opacity-map slot/state but does not infer alpha/cutout behavior from a generic numeric V-Ray opacity value. This keeps the supported signal tied to the renderer-specific cutout path instead of treating all reduced V-Ray opacity as equivalent to a foliage mask.

## Detection failure policy

`getPropNames()` is used to discover runtime-exposed property names so the detector can resolve case-insensitive Max property names safely. If property enumeration fails for a graph node, the detector does not guess arbitrary property names and therefore does not create a protection finding from that node. This is a deliberate fail-open choice for the property-enumeration layer; the known-slot checks remain state-based whenever Max exposes those slots.

## BlendMax implication

Join Mesh by Material currently stages and can split Multi/Sub geometry before joining material buckets. For alpha/opacity assets, the safest Skip behavior is therefore to detect the assigned material graph first and exclude the entire source geometry node before staging/splitting.

For Multi/Sub materials, whole-node protection is intentional: if any nested material/map path is alpha/opacity-sensitive, the complete source node is skipped. No face-level analysis is required for this PR.
