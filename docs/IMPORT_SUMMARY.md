# Blender Import Summary

BlendMax shows a compact completion dialog after a successful `.blendmax` import.

## Layout

The dialog presents:

- asset name;
- imported object count;
- material count;
- packaged-texture/image count;
- actionable warning count;
- compatibility-note count.

Warnings and compatibility notes are shown in separate sections. Known expected
limitations remain informational; unexpected importer problems stay warnings.

A clean import explicitly states that no warnings or compatibility notes were
generated.

## Scope

The summary is a presentation layer over the existing `ImportSummary` data. It
does not change material conversion, object reconstruction, warning generation,
or diagnostic categorization.

Existing console output remains available for debugging and automated workflows.
The popup is only shown after a successful import; import exceptions continue to
use the existing error-reporting path.
