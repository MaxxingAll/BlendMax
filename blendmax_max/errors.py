"""BlendMax-specific exceptions."""

from __future__ import annotations


class BlendMaxError(RuntimeError):
    code = "BLENDMAX_ERROR"


class SceneValidationError(BlendMaxError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ExportError(BlendMaxError):
    code = "EXPORT_FAILED"


class CleanupError(BlendMaxError):
    code = "CLEANUP_FAILED"
