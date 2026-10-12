# BlendMax

3ds Max exporter (`blendmax_max/`, AppBundle in `appbundle/`) and Blender
importer extension (`blendmax_blender/`), sharing `blendmax_archive_policy.py`.
See `README.md` for the product and `CHANGELOG.md` for release history.

- Tests: `python -m unittest discover -s tests` (Python 3.11+, no host apps
  needed). CI runs the same on 3.11, 3.12 and 3.13.
- Read `docs/AGENT_WORKFLOW.md` before any GitHub write (PRs, issues, CI) or
  live host test in Blender or 3ds Max. It covers the GitHub App helper, the
  V-Ray headless workaround and how to install test builds.
- Never commit keys, tokens or test-only builds.
