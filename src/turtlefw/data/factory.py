"""Provider construction.

Callers must not instantiate ``TushareProvider`` directly: construction lives
here so a second provider (Wind, iFinD) can be selected with
``TURTLE_PROVIDER`` without touching the CLI, and so tests can inject a fake.

The kind is read from the explicit argument first, then the environment, then
``DEFAULT_KIND``.  Unknown kinds raise :class:`ProviderError` instead of
silently falling back to Tushare.
"""

from __future__ import annotations

import os
from pathlib import Path

from .protocol import Provider, ProviderError

DEFAULT_KIND = "tushare"
SUPPORTED_KINDS: tuple[str, ...] = ("tushare",)


def provider_kind(kind: str | None = None) -> str:
    """Resolve the provider kind from argument, environment, or default."""
    value = kind or os.environ.get("TURTLE_PROVIDER") or DEFAULT_KIND
    return value.strip().lower()


def build_provider(
    *,
    kind: str | None = None,
    token: str | None = None,
    cache_dir: Path | str | None = None,
    ttl_seconds: int | None = None,
    min_interval: float | None = None,
    max_retries: int = 3,
) -> Provider:
    """Build a provider instance for the requested kind."""
    name = provider_kind(kind)
    if name == "tushare":
        from ..config import get_token
        from .tushare_provider import TushareProvider

        return TushareProvider(
            token if token is not None else get_token(),
            cache_dir=Path(cache_dir) if cache_dir is not None else None,
            ttl_seconds=ttl_seconds,
            min_interval=0.35 if min_interval is None else min_interval,
            max_retries=max_retries,
        )
    raise ProviderError(
        f"未知的数据源：{name}（可选：{', '.join(SUPPORTED_KINDS)}；"
        "可用 TURTLE_PROVIDER 环境变量指定）"
    )
