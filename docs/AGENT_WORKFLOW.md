# Agent Workflow Notes

How AI coding sessions (Claude Code and similar) work with this repository and
the maintainer's machine. Nothing here is a secret: no keys or tokens belong
in this repository, ever.

## GitHub: pull requests, issues and CI

The `gh` CLI is not installed on the maintainer's Windows machine, and MCP
GitHub connectors have returned `403 Resource not accessible by integration`
on writes. GitHub writes therefore go through the maintainer's own GitHub App,
**claude-tan**. Pull requests and comments it creates are authored by
`claude-tan[bot]`.

### Local sessions (maintainer's Windows machine)

The helper lives outside the repository in `%USERPROFILE%\.config\github-app\`:

| File | Purpose |
| --- | --- |
| `gh_app.py` | Signs in as the app and calls the GitHub REST API |
| `config.json` | App ID and the private key's path |
| `*.private-key.pem` | The app's private key. Never read, print, copy or commit it |

From Git Bash, with Python 3.11+ and `pyjwt[crypto]` installed:

```bash
cd ~/.config/github-app

# Confirm the installation and its permissions
py -3 gh_app.py check MaxxingAll/BlendMax

# Any REST call; prints {"status": ..., "response": ...}
MSYS_NO_PATHCONV=1 py -3 gh_app.py api GET "/repos/MaxxingAll/BlendMax/pulls?state=open"
MSYS_NO_PATHCONV=1 py -3 gh_app.py api POST /repos/MaxxingAll/BlendMax/pulls --data-file pr.json
```

`pr.json` holds `{"title", "head", "base", "body"}`. Issues use
`POST /repos/MaxxingAll/BlendMax/issues` with `{"title", "body"}`. CI results
come from `GET /repos/MaxxingAll/BlendMax/commits/<sha>/check-runs`.

Gotchas:

- Set `MSYS_NO_PATHCONV=1`, or Git Bash rewrites `/repos/...` into a Windows
  file path before Python sees it.
- Use `py -3`. A bare `python` may hit the Microsoft Store alias.
- If a create call errors while printing its output, the request may still have
  succeeded. Look the object up (for example
  `GET /pulls?head=MaxxingAll:<branch>&state=all`) before retrying, so nothing
  is created twice.
- Pushing uses normal `git push` credentials, not the app.
- The desktop app's PR tracking needs `gh`, so it cannot bind these PRs. Read
  CI through the helper instead.

### Cloud sessions

Cloud sessions do not have the helper or the private key, and the key must
never be copied there. Use the session's own GitHub access, or the **Claude**
GitHub App (Claude Code GitHub Actions) that is installed on this account.

## Live host testing

Unit tests run with ordinary Python (`python -m unittest discover -s tests`).
Real `bpy`, `pymxs`, FBX and UI behaviour must be checked in the hosts.

### Blender 5.2

- **Headless runs hang** with the maintainer's preferences, because V-Ray for
  Blender Community Edition refuses background mode. Use
  `py -3 tools/blender_headless.py --timeout 120 -- <blender args>` (see the
  README). Do not save preferences from those runs.
- Blender's `--command extension install-file` hangs for the same reason.
  Build with `tools/build_blender_extension.py` and unzip the result into
  `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\blendmax_importer`.
  Back up the existing folder first.
- To simulate a BlendMax update in a running Blender, start it with
  `--python <script>` that sets
  `bpy.app.driver_namespace["blendmax.running_version"]` to an older version,
  resets `restart_notice._last_mtime`, calls `restart_notice._poll()`, then
  runs `bpy.ops.ed.undo_push()` to fire the popup.
- Every Blender process shares the restart-notice state file, so close stray
  Blender instances before testing the notice.

### 3ds Max 2025

- Startup takes roughly 75 seconds. Wait for the main window to respond before
  driving it.
- The bundle lives in `%APPDATA%\Autodesk\ApplicationPlugins\BlendMax.bundle`.
  Back it up first. Install from a checkout with
  `py -3 -c "import blendmax_install; blendmax_install.install_from_source('.')"`.
- Test-only builds (for example installers with log markers) belong in a
  scratch folder, never in this repository. Reinstall a clean build afterwards.

### Driving the UI

Screenshot tools may return blank images for Blender's and 3ds Max's GPU-drawn
windows. A desktop capture through PowerShell
(`System.Drawing.Graphics.CopyFromScreen`, DPI-aware) shows them correctly, so
capture that way and scale the coordinates to the clicking tool's frame.
