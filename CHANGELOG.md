# BlendMax Changelog

This file records user-visible changes to the 3ds Max exporter/cleanup and the
Blender importer. BlendMax is still alpha software; host-tested baselines are
called out separately from automated coverage.

## Blender Importer 0.1.8 — 2026-09-08

### Added

- Adds a **Reload BlendMax** control in Add-on Preferences for a one-shot,
  deferred in-process reload of the currently installed Blender extension copy.
- Reload purges the active package and its submodules from `sys.modules` before
  re-enabling the same installed extension, so newly installed code can be
  loaded without restarting Blender.
- A successful reload consumes the pending restart notice on that first
  registration, including when the installed version is newer than the running
  module. No second reload is required just to clear the notice.
- Duplicate clicks while a reload is already queued are ignored.
- Reload failures print the full traceback and restore the normal restart-notice
  state so a failed reload is not treated as successful.

### Changed

- Restart-notice suppression is represented by a one-shot current-process reload
  marker rather than a sticky version flag. The marker is consumed only by the
  registration produced by the requested reload, so later genuine update/restart
  states can surface normally.

### Release metadata

- Bumps the Blender importer and extension manifest version to **0.1.8**.

### Verification

- Restored direct coverage for the ordinary one-restart state transition.
- Added coverage that a first successful hot reload consumes the notice and that
  a failed reload restores it.
- Real Blender extension install/reload verification remains a host-level gate
  because the ordinary Python CI suite does not import `bpy`.

## Blender Importer 0.1.7 — 2026-09-04

### Added
