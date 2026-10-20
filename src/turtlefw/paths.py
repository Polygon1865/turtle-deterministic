"""Resolve the writable runtime root for reports and run state.

The default runtime root is ``.runs/`` so every command writes to the same
workspace-local directory. ``TURTLE_OUTPUT_DIR`` / ``TURTLE_OUTPUT_ROOT`` or
the global ``--output-dir`` option can still override it explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_OUTPUT_DIR = ".runs"
ENV_ALIASES = ("TURTLE_OUTPUT_DIR", "TURTLE_OUTPUT_ROOT")


def output_root() -> Path:
    """Return the configured runtime root without creating it."""
    for name in ENV_ALIASES:
        raw = os.environ.get(name, "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path(DEFAULT_OUTPUT_DIR)


def output_path(code: str, *parts: str) -> Path:
    return output_root() / str(code) / Path(*parts)


def ensure_output_root() -> Path:
    root = output_root()
    root.mkdir(parents=True, exist_ok=True)
    return root
