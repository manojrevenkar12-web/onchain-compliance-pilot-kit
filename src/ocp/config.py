"""Loads the YAML files in config/. Each package reads only the files it owns (AGENTS.md)."""

from __future__ import annotations

import copy
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

_SRC_ROOT = Path(__file__).resolve().parents[2]
# the repository root in a checkout; OCP_ROOT (or the working directory) when installed as a package
ROOT = Path(os.environ.get("OCP_ROOT", _SRC_ROOT if (_SRC_ROOT / "config").is_dir() else Path.cwd()))
CONFIG = ROOT / "config"
REPORTS = ROOT / "reports"


@cache
def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((CONFIG / f"{name}.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict), name
    return data


def kit() -> dict[str, Any]:
    return copy.deepcopy(_load("kit"))


def designs() -> dict[str, Any]:
    return copy.deepcopy(_load("designs"))


def seeds() -> dict[str, Any]:
    return copy.deepcopy(_load("seeds"))


def gates() -> dict[str, Any]:
    return copy.deepcopy(_load("gates"))


def prospect(name: str) -> dict[str, Any]:
    """What the customer told us in discovery. The kit may read this; it is not the truth about their customers."""
    folder = "prospects" if (CONFIG / "prospects" / f"{name}.yml").exists() else "heldout"
    return copy.deepcopy(_load(f"{folder}/{name}"))


def prospect_names(split: str = "dev") -> list[str]:
    folder = "heldout" if split == "heldout" else "prospects"
    return sorted(p.stem for p in (CONFIG / folder).glob("*.yml"))
