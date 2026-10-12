"""Tests for tools/github_app.py; GitHub is never contacted.

Credential resolution and path parsing need only the standard library. The
JWT test runs only where pyjwt[crypto] is installed (CI does not install it).
"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import github_app

PEM = "-----BEGIN RSA PRIVATE KEY-----\nTEST\n-----END RSA PRIVATE KEY-----\n"


class LoadCredentialsTests(unittest.TestCase):
    def test_base64_environment_variable(self):
        encoded = base64.b64encode(PEM.encode("utf-8")).decode("ascii")
        credentials = github_app.load_credentials(
            {"GITHUB_APP_ID": "42", "GITHUB_APP_PRIVATE_KEY_B64": encoded},
            config_path=Path("missing.json"),
        )
        self.assertEqual(credentials, github_app.AppCredentials("42", PEM, "environment"))

    def test_plain_environment_variable_restores_escaped_newlines(self):
        flattened = PEM.replace("\n", "\\n")
        credentials = github_app.load_credentials(
            {"GITHUB_APP_ID": "42", "GITHUB_APP_PRIVATE_KEY": flattened},
            config_path=Path("missing.json"),
        )
        self.assertEqual(credentials.private_key, PEM)

    def test_invalid_base64_is_reported(self):
        with self.assertRaises(github_app.CredentialsError):
            github_app.load_credentials(
                {"GITHUB_APP_ID": "42", "GITHUB_APP_PRIVATE_KEY_B64": "not base64!"},
                config_path=Path("missing.json"),
            )

    def test_environment_wins_over_config_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self._write_config(Path(temporary), "7")
            encoded = base64.b64encode(PEM.encode("utf-8")).decode("ascii")
            credentials = github_app.load_credentials(
                {"GITHUB_APP_ID": "42", "GITHUB_APP_PRIVATE_KEY_B64": encoded},
                config_path=config,
            )
        self.assertEqual(credentials.app_id, "42")

    def test_config_file_used_without_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self._write_config(Path(temporary), "7")
            credentials = github_app.load_credentials({}, config_path=config)
        self.assertEqual(credentials.app_id, "7")
        self.assertEqual(credentials.private_key, PEM)
        self.assertEqual(credentials.source, str(config))

    def test_app_id_alone_falls_back_to_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self._write_config(Path(temporary), "7")
            credentials = github_app.load_credentials(
                {"GITHUB_APP_ID": "42"}, config_path=config
            )
        self.assertEqual(credentials.app_id, "7")

    def test_missing_everything_is_reported(self):
        with self.assertRaises(github_app.CredentialsError):
            github_app.load_credentials({}, config_path=Path("does/not/exist.json"))

    def test_main_reports_missing_credentials_without_traceback(self):
        with mock.patch.object(
            github_app, "load_credentials", side_effect=github_app.CredentialsError("none")
        ), mock.patch("sys.stderr"):
            self.assertEqual(github_app.main(["check", "o/r"]), 2)

    @staticmethod
    def _write_config(root, app_id):
        key = root / "app.private-key.pem"
        key.write_text(PEM, encoding="utf-8")
        config = root / "config.json"
        config.write_text(
            json.dumps({"app_id": int(app_id), "private_key_path": str(key)}),
            encoding="utf-8",
        )
        return config


class RepoFromPathTests(unittest.TestCase):
    def test_repo_is_taken_from_the_path(self):
        self.assertEqual(
            github_app.repo_from_path("/repos/MaxxingAll/BlendMax/pulls?state=all"),
            "MaxxingAll/BlendMax",
        )

    def test_non_repo_path_is_rejected(self):
        for path in ("/app", "/repos/only-owner", "C:/Program Files/Git/repos/a/b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                github_app.repo_from_path(path)


class AppJwtTests(unittest.TestCase):
    def test_jwt_is_signed_with_the_app_id_as_issuer(self):
        try:
            import jwt
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError:
            self.skipTest("pyjwt[crypto] is not installed")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode("ascii")
        token = github_app.app_jwt(github_app.AppCredentials("42", pem, "test"), now=1000)
        claims = jwt.decode(
            token, key.public_key(), algorithms=["RS256"], options={"verify_exp": False}
        )
        self.assertEqual(claims, {"iat": 940, "exp": 1540, "iss": "42"})


if __name__ == "__main__":
    unittest.main()
