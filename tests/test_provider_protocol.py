"""Provider protocol v2 must stay in sync with the real provider.

The v1 contract listed seven methods while the app called thirty, so a second
provider could not be checked.  These tests fail as soon as the protocol and
``TushareProvider`` drift apart, or as soon as a caller bypasses the factory.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from turtlefw.data.factory import build_provider
from turtlefw.data.protocol import Provider, ProviderError
from turtlefw.data.tushare_provider import TushareProvider


def _protocol_members() -> dict[str, object]:
    return {
        name: value
        for name, value in Provider.__dict__.items()
        if not name.startswith("_") and name not in {"name"}
    }


def _param_shape(func: object) -> list[tuple[str, int, object]]:
    signature = inspect.signature(func)
    return [
        (parameter.name, parameter.kind, parameter.default)
        for parameter in signature.parameters.values()
        if parameter.name != "self"
    ]


def test_every_protocol_member_exists_on_tushare() -> None:
    missing = [name for name in _protocol_members() if not hasattr(TushareProvider, name)]
    assert missing == []


@pytest.mark.parametrize("member", sorted(_protocol_members()))
def test_protocol_signature_matches_tushare(member: str) -> None:
    declared = _protocol_members()[member]
    actual = getattr(TushareProvider, member)
    if isinstance(declared, property):
        assert isinstance(actual, property), f"{member} 在协议里是属性，实现里不是"
        return
    assert _param_shape(declared) == _param_shape(actual), (
        f"{member} 的参数与实现不一致：\n"
        f"协议 {_param_shape(declared)}\n实现 {_param_shape(actual)}"
    )


def test_factory_builds_tushare_provider() -> None:
    provider = build_provider(token="test-token", min_interval=0.01)
    assert isinstance(provider, TushareProvider)
    assert provider.name == "tushare"


def test_factory_rejects_unknown_kind() -> None:
    with pytest.raises(ProviderError, match="未知的数据源"):
        build_provider(kind="wind", token="test-token")


def test_factory_reads_kind_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURTLE_PROVIDER", "wind")
    with pytest.raises(ProviderError, match="wind"):
        build_provider(token="test-token")


def test_source_never_constructs_provider_directly() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "turtlefw"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.parent.name == "data" and path.name in {"tushare_provider.py", "factory.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "TushareProvider(" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_protocol_covers_every_provider_call() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "turtlefw"
    used: set[str] = set()
    pattern = re.compile(r"(?:\bprovider|self\.provider)\.([a-z_][a-z0-9_]*)")
    for path in root.rglob("*.py"):
        used.update(pattern.findall(path.read_text(encoding="utf-8")))
    declared = set(_protocol_members()) | {"name"}
    missing = sorted(name for name in used if name not in declared)
    assert missing == [], f"这些 provider 方法没有写进协议：{missing}"
