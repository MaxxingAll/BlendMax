# Alpha/Opacity Research Notes

## 3ds Max

3ds Max material APIs expose opacity and opacity-map state, including explicit map and enable properties. This supports detection from actual material state rather than material-name heuristics.

Autodesk references:

- Standard material / opacity and opacity-map properties: https://help.autodesk.com/cloudhelp/2025/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Material-MAXWrapper/Material-Types/GUID-57F5EBBA-5F54-4CD4-8993-0B07A3571293.html
- Multi/Sub-Object material API: https://help.autodesk.com/cloudhelp/2021/ENU/3DSMax-MAXScript/files/GUID-7ECB1E85-6199-4143-BEDA-3B26DD35E0C3.htm

## V-Ray

Chaos documents an opacity-map workflow for leaf cutouts where the opacity map determines which portions of a leaf surface are visible.

Chaos reference:

- V-Ray for 3ds Max — How to Make Leaves: https://docs.chaos.com/display/VMAX/How%2Bto%2BMake%2BLeaves

## BlendMax implication

Join Mesh by Material currently stages and can split Multi/Sub geometry before joining material buckets. For alpha/opacity assets, the safest Skip behavior is therefore to detect the assigned material graph first and exclude the entire source geometry node before staging/splitting.

For Multi/Sub materials, whole-node protection is intentional: if any nested material/map path is alpha/opacity-sensitive, the complete source node is skipped. No face-level analysis is required for this PR.
