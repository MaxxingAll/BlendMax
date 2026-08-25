"""Importer-specific exceptions."""

from __future__ import annotations


class BlendMaxImportError(RuntimeError):
    """A user-facing BlendMax import failure."""


class PackageValidationError(BlendMaxImportError):
    """The selected .blendmax archive is malformed or unsafe."""


class ManifestValidationError(BlendMaxImportError):
    """The package manifest is missing required conversion data."""
