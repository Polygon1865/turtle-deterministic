"""Test-local temp directories.

The DSH Windows sandbox can deny pytest's default numbered-directory creation
under %TEMP%, even though a plain ``Path.mkdir`` in the same area works. This
fixture gives tests a stable writable base without depending on that path.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


class _Factory:
    def __init__(self, base: Path) -> None:
        self._base = base
        self._counter = 0
        self._retention_policy = "failed"

    def getbasetemp(self) -> Path:
        return self._base

    def mktemp(self, basename: str = "", numbered: bool = True) -> Path:
        name = basename or "tmp"
        if numbered:
            self._counter += 1
            name = f"{name}{self._counter}"
        path = self._base / name
        path.mkdir(parents=True, exist_ok=True)
        return path


@pytest.fixture(scope="session")
def tmp_path_factory():
    base = Path(tempfile.gettempdir()) / f"turtle-pytest-{os.getpid()}"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    yield _Factory(base)
    shutil.rmtree(base, ignore_errors=True)
