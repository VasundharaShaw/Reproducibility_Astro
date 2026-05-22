"""
pipeline/reproscore/scoring/rubric.py
======================================
Community rubric loader and validator.

Vendored from github.com/myVSR/reproscore — do not edit directly.
One change from upstream: added project-root candidate to YAML search path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_DEFAULTS: Dict[str, Any] = {
    "name": "default",
    "version": "1.0",
    "categories": {
        "E": {"weight": 0.30, "tau": 40, "k": 1.5},
        "A": {"weight": 0.25, "tau": 30, "k": 1.5},
        "D": {"weight": 0.20, "tau": 20, "k": 1.2},
        "C": {"weight": 0.15, "tau": 25, "k": 1.2},
        "S": {"weight": 0.10, "tau": 30, "k": 1.2},
    },
    "penalties": {
        "environment_hard_threshold": 10,
        "data_hard_threshold": 10,
        "environment_hard_penalty": 20,
        "data_hard_penalty": 15,
        "seed_threshold": 50,
        "seed_penalty": 10,
    },
    "ros_components": {
        "I":     {"weight": 0.30},
        "X":     {"weight": 0.25},
        "delta": {"weight": 0.20},
        "N":     {"weight": 0.10},
        "E":     {"weight": 0.10},
        "T":     {"weight": 0.05},
    },
    "rcs": {
        "alpha_max": 0.70,
        "alpha_min": 0.10,
    },
}


@dataclass
class Rubric:
    name: str
    version: str
    categories: Dict[str, Dict[str, float]]
    penalties: Dict[str, float]
    ros_components: Dict[str, Dict[str, float]]
    rcs: Dict[str, float]

    def validate(self):
        cat_sum = sum(v["weight"] for v in self.categories.values())
        if abs(cat_sum - 1.0) > 0.01:
            raise ValueError(
                f"Category weights must sum to 1.0 ± 0.01, got {cat_sum:.4f}"
            )
        ros_sum = sum(v["weight"] for v in self.ros_components.values())
        if abs(ros_sum - 1.0) > 0.01:
            raise ValueError(
                f"ROS component weights must sum to 1.0 ± 0.01, got {ros_sum:.4f}"
            )


def load_rubric(path: Optional[str | Path] = None) -> Rubric:
    """
    Load a rubric from YAML file, or return the built-in defaults.

    Search order when no explicit path is given:
      1. project_root/config/default_rubric.yaml  (Reproducibility_Astro layout)
      2. config/default_rubric.yaml               (relative to CWD)
      3. default_rubric.yaml                      (CWD fallback)
    Falls back to hardcoded defaults if yaml is unavailable or no file found.
    """
    data = dict(_DEFAULTS)

    if path is None:
        # parent = scoring/, parent.parent = reproscore/, parent.parent.parent = pipeline/
        # parent.parent.parent.parent = project root
        candidates = [
            Path(__file__).parent.parent.parent.parent / "config" / "default_rubric.yaml",
            Path("config/default_rubric.yaml"),
            Path("default_rubric.yaml"),
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if path and _YAML_AVAILABLE:
        try:
            with open(path, "r") as f:
                loaded = yaml.safe_load(f)
            if loaded:
                data = loaded
        except Exception as e:
            import warnings
            warnings.warn(f"Could not load rubric from {path}: {e}. Using defaults.")

    rubric = Rubric(
        name=data.get("name", "default"),
        version=str(data.get("version", "1.0")),
        categories=data.get("categories", _DEFAULTS["categories"]),
        penalties=data.get("penalties", _DEFAULTS["penalties"]),
        ros_components=data.get("ros_components", _DEFAULTS["ros_components"]),
        rcs=data.get("rcs", _DEFAULTS["rcs"]),
    )
    rubric.validate()
    return rubric
