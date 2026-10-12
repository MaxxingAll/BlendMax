"""Call the GitHub REST API as a GitHub App installation.

Used by AI coding sessions to open pull requests and issues and to read CI;
see docs/AGENT_WORKFLOW.md. The app's credentials come from, in order:

1. Environment variables (cloud sessions):
   ``GITHUB_APP_ID`` and ``GITHUB_APP_PRIVATE_KEY_B64`` (the PEM file,
   base64-encoded onto one line) or ``GITHUB_APP_PRIVATE_KEY`` (the PEM text).
2. A config file (local sessions), ``--config`` or by default
   ``~/.config/github-app/config.json``::

       {"app_id": 123456, "private_key_path": "C:/.../app.private-key.pem"}

The private key signs a 10-minute app JWT, which is exchanged for a 1-hour
installation token for the repository's installation. Neither the key nor
any token is ever printed; only API responses are.

Usage::

    python tools/github_app.py check OWNER/REPO
    python tools/github_app.py api METHOD PATH [--data-file FILE.json]

PATH is relative to https://api.github.com and must start with
``/repos/OWNER/REPO``. Requires ``pyjwt[crypto]``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping, NamedTuple, Optional

API = "https://api.github.com"
DEFAULT_CONFIG = Path.home() / ".config" / "github-app" / "config.json"


class AppCredentials(NamedTuple):
    app_id: str
    private_key: str
    source: str


class CredentialsError(RuntimeError):
    """The app's credentials are missing or malformed."""


def load_credentials(
    environ: Optional[Mapping[str, str]] = None,
    config_path: Optional[Path] = None,
) -> AppCredentials:
    """Resolve the app ID and private key; environment variables win."""

    values = os.environ if environ is None else environ
    app_id = values.get("GITHUB_APP_ID", "").strip()
    encoded = values.get("GITHUB_APP_PRIVATE_KEY_B64", "").strip()
    plain = values.get("GITHUB_APP_PRIVATE_KEY", "")
    if app_id and (encoded or plain.strip()):
        if encoded:
            try:
                key = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise CredentialsError(
                    "GITHUB_APP_PRIVATE_KEY_B64 is not valid base64 of a PEM file."
                ) from exc
        else:
            # Some secret stores flatten newlines to a literal "\n".
            key = plain.replace("\\n", "\n")
        return AppCredentials(app_id, key, "environment")

    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG
    if not path.is_file():
        raise CredentialsError(
            "No GitHub App credentials: set GITHUB_APP_ID and "
            "GITHUB_APP_PRIVATE_KEY_B64, or create {0}.".format(path)
        )
    config = json.loads(path.read_text(encoding="utf-8"))
    try:
        key = Path(config["private_key_path"]).read_text(encoding="utf-8")
        return AppCredentials(str(config["app_id"]), key, str(path))
    except KeyError as exc:
        raise CredentialsError("{0} is missing {1}.".format(path, exc)) from exc
    except OSError as exc:
        raise CredentialsError("Could not read the private key: {0}".format(exc)) from exc


def app_jwt(credentials: AppCredentials, now: Optional[int] = None) -> str:
    import jwt  # pyjwt[crypto]; imported here so the rest stays dependency-free

    issued = int(time.time()) if now is None else now
    # iat is backdated 60 s for clock drift, as GitHub recommends.
    payload = {"iat": issued - 60, "exp": issued + 9 * 60, "iss": credentials.app_id}
    return jwt.encode(payload, credentials.private_key, algorithm="RS256")


def repo_from_path(path: str) -> str:
    parts = path.split("?", 1)[0].strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "repos" and parts[1] and parts[2]:
        return parts[1] + "/" + parts[2]
    raise ValueError("PATH must start with /repos/OWNER/REPO: {0}".format(path))


def _request(method, path, bearer, data=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(
        API + path,
        data=body,
        method=method.upper(),
        headers={
            "Authorization": "Bearer " + bearer,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "blendmax-github-app",
        },
    )
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = raw.decode("utf-8", "replace")
        return error.code, detail


def _installation_token(credentials, repo):
    token = app_jwt(credentials)
    status, installation = _request("GET", "/repos/{0}/installation".format(repo), token)
    if status != 200:
        raise SystemExit(
            "The app is not installed on {0} (HTTP {1}): {2}".format(repo, status, installation)
        )
    status, access = _request(
        "POST",
        "/app/installations/{0}/access_tokens".format(installation["id"]),
        token,
        data={},
    )
    if status != 201:
        raise SystemExit(
            "Could not get an installation token (HTTP {0}): {1}".format(status, access)
        )
    return access["token"], access.get("permissions", {}), installation


def _print(value) -> None:
    # ASCII escapes keep any console code page (e.g. cp1252) printable.
    print(json.dumps(value, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, help="Config file for local sessions")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Show the app, installation and permissions")
    check.add_argument("repo")
    api = commands.add_parser("api", help="Call the REST API as the installation")
    api.add_argument("method")
    api.add_argument("path")
    api.add_argument("--data-file", type=Path)
    options = parser.parse_args(argv)

    try:
        credentials = load_credentials(config_path=options.config)
    except CredentialsError as exc:
        print(exc, file=sys.stderr)
        return 2

    if options.command == "check":
        status, app = _request("GET", "/app", app_jwt(credentials))
        if status != 200:
            print("App authentication failed (HTTP {0}): {1}".format(status, app), file=sys.stderr)
            return 1
        _token, permissions, installation = _installation_token(credentials, options.repo)
        _print({
            "app": app.get("slug"),
            "credentials": credentials.source,
            "installation_id": installation["id"],
            "account": installation["account"]["login"],
            "repository_selection": installation.get("repository_selection"),
            "permissions": permissions,
        })
        return 0

    try:
        repo = repo_from_path(options.path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    data = None
    if options.data_file is not None:
        data = json.loads(options.data_file.read_text(encoding="utf-8"))
    token, _permissions, _installation = _installation_token(credentials, repo)
    status, result = _request(options.method, options.path, token, data)
    _print({"status": status, "response": result})
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
