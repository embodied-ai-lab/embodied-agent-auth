"""Load the four small repository YAML configuration files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def repository_root() -> Path:
    configured = os.environ.get("ISCPS_LAB_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[4]


def load_yaml(name: str, root: Path | None = None) -> dict[str, Any]:
    base = repository_root() if root is None else root
    path = base / "configs" / name
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


@dataclass(frozen=True)
class LabConfig:
    root: Path
    scenario: dict[str, Any]
    topics: dict[str, Any]
    vlm: dict[str, Any]
    sst: dict[str, Any]

    @classmethod
    def load(cls, root: Path | None = None) -> LabConfig:
        base = repository_root() if root is None else root.resolve()
        return cls(
            root=base,
            scenario=load_yaml("scenario.yaml", base),
            topics=load_yaml("topics.yaml", base),
            vlm=load_yaml("vlm.yaml", base),
            sst=load_yaml("sst.yaml", base),
        )

    def resolve(self, value: str) -> Path:
        return (self.root / value).resolve()
