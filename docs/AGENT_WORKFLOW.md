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

The tool is `tools/github_app.py` (needs `pyjwt[crypto]`). It holds no
secrets; the app's credentials come from the session.

### Local sessions (maintainer's Windows machine)

Credentials live outside the repository in `%USERPROFILE%\.config\github-app\`:

| File | Purpose |
| --- | --- |
| `config.json` | `{"app_id": ..., "private_key_path": ...}` |
| `*.private-key.pem` | The app's private key. Never read, print, copy or commit it |

From Git Bash at the repository root:

```bash
# Confirm the installation and its permissions
MSYS_NO_PATHCONV=1 py -3 tools/github_app.py check MaxxingAll/BlendMax

# Any REST call; prints {"status": ..., "response": ...}
MSYS_NO_PATHCONV=1 py -3 tools/github_app.py api GET "/repos/MaxxingAll/BlendMax/pulls?state=open"
MSYS_NO_PATHCONV=1 py -3 tools/github_app.py api POST /repos/MaxxingAll/BlendMax/pulls --data-file pr.json
```

### Cloud sessions (Claude Code on the web)

Do **not** use the GitHub App or its key in cloud sessions. Cloud
environment variables are readable by anyone using the environment, and
network secrets cannot hold a key that must sign requests inside the session.

Cloud sessions do not need it: the built-in GitHub proxy authenticates the
session's GitHub tools, `git push` and `gh` (where `GH_TOKEN` reads as the
placeholder `proxy-injected`) with the maintainer's own credentials, without
the token entering the session. Use those to push branches, open pull
requests and issues, and read CI. See
<https://code.claude.com/docs/en/cloud-environments#github-proxy>.

The tool's `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY_B64` environment
variables exist only for a real secret store, such as GitHub Actions
secrets, should a workflow ever need to act as the app.

### Calls and gotchas

`pr.json` holds `{"title", "head", "base", "body"}`. Issues use
`POST /repos/MaxxingAll/BlendMax/issues` with `{"title", "body"}`. CI results
come from `GET /repos/MaxxingAll/BlendMax/commits/<sha>/check-runs`.

- Set `MSYS_NO_PATHCONV=1` in Git Bash, or it rewrites `/repos/...` into a
  Windows file path before Python sees it.
- Use `py -3` on Windows. A bare `python` may hit the Microsoft Store alias.
- If a create call errors while printing its output, the request may still have
  succeeded. Look the object up (for example
  `GET /pulls?head=MaxxingAll:<branch>&state=all`) before retrying, so nothing
  is created twice.
- Pushing uses normal `git push` credentials, not the app.

### Commit identity

Agent commits are authored by the app's bot account, with the maintainer
credited as co-author. Pass the identity per commit (never set it in git
config, so the maintainer's own commits stay theirs):

```bash
git -c user.name="claude-tan[bot]" \
    -c user.email="341245867+claude-tan[bot]@users.noreply.github.com" \
    commit -m "<subject>" -m "<body>

Co-Authored-By: Alleluia <dluffys97@gmail.com>"
```

The email is the bot's GitHub no-reply address (user ID `341245867`), so
GitHub links the commit to `claude-tan[bot]`. The maintainer is the only
co-author: by the maintainer's choice, agent commits carry no separate
Claude co-author line.
- The desktop app's PR tracking needs `gh`, so it cannot bind these PRs. Read
  CI through the tool instead.

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
