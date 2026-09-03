# Release Versioning

The 3ds Max exporter version is tracked in `blendmax_max/__init__.py` and mirrored in the AppBundle manifest.

For Max exporter alpha releases, the human-readable version follows the `0.1.0-alpha.4.x.0` format. The AppBundle `FriendlyVersion` mirrors that value, while `AppVersion` and component versions advance their final numeric component for each Max exporter release.
