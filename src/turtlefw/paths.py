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
CACHE_ENV = "TURTLE_CACHE_DIR"


def cache_root(runs_root: Path | str | None = None) -> Path:
    """Return one shared HTTP cache location.

    Daily runs used to keep a cache per day directory, so every new day paid
    the cold-start crawl of ~1.7k HK indicator calls; on 2026-10-30 that
    pushed the HK screen past its 1800s timeout and the whole day produced no
    reports.  One cache across days keeps reports frozen while making the
    crawl a one-off.  ``TURTLE_CACHE_DIR`` overrides everything.
    """

    raw = os.environ.get(CACHE_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    if runs_root is not None:
        return Path(runs_root).parent / ".cache"
    return output_root() / ".cache"


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
