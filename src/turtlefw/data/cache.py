"""Content-addressed file cache with TTL.

The key covers the endpoint, every request parameter and the schema version,
so a change in either cannot silently reuse stale data.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping


class FileCache:
    def __init__(self, root: Path, ttl_seconds: int = 7 * 86400) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def make_key(endpoint: str, params: Mapping[str, Any], schema_version: str) -> str:
        payload = json.dumps(
            {"endpoint": endpoint, "params": dict(sorted(params.items())), "v": schema_version},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.is_file():
            return None
        if self.ttl_seconds >= 0 and time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, value: Any) -> None:
        path = self._path(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(value, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)

    def clear(self) -> int:
        removed = 0
        for path in self.root.glob("*.json"):
            path.unlink(missing_ok=True)
            removed += 1
        return removed
