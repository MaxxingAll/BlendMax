"""Pure-Python data models shared by validation and export code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class SceneNode:
    node_id: str
    name: str
    node_type: str
    superclass: str
    parent_id: Optional[str] = None
    is_group_head: bool = False
    is_group_member: bool = False
    exportable: bool = True


@dataclass(frozen=True)
class ValidationResult:
    mode: str
    root_id: str
    payload_ids: Tuple[str, ...]
    export_ids: Tuple[str, ...]
    warnings: Tuple[str, ...] = ()

    @property
    def object_count(self) -> int:
        return len(self.payload_ids)


@dataclass(frozen=True)
class SizePolicyResult:
    dimensions_m: Tuple[float, float, float]
    recommended_scale: float
    oversized: bool

