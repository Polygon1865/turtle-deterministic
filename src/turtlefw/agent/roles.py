"""Four-role research contract (ADR-05).

Extractor -> Researcher -> Writer -> Auditor.  Each role declares a purpose, a
tool whitelist and an output schema; the pipeline refuses tools that are not on
the list, so a role cannot silently acquire more reach than it was designed
with.  The Auditor is deterministic: it re-validates the assembled payload with
the same validators that guard ``research.json`` today (structure, placeholders,
quality), plus the language check from the single-role agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


class RoleError(RuntimeError):
    """A role produced output that violates its schema."""


class ToolNotAllowed(RoleError):
    def __init__(self, tool: str, role: str) -> None:
        super().__init__(f"tool {tool!r} is not allowed for role {role!r}")
        self.tool = tool
        self.role = role


@dataclass(frozen=True, slots=True)
class RoleSpec:
    name: str
    purpose: str
    tools: tuple[str, ...]
    uses_llm: bool


EXTRACTOR = RoleSpec(
    name="extractor",
    purpose="从快照与数据包里抽取可引用的证据候选，不改写数字、不做判断",
    tools=("read_metrics", "read_data_pack"),
    uses_llm=True,
)
RESEARCHER = RoleSpec(
    name="researcher",
    purpose="仅基于已抽取证据写 D1-D6 claims 与 params，缺证据就写 unknown",
    tools=("read_evidence", "read_metrics"),
    uses_llm=True,
)
WRITER = RoleSpec(
    name="writer",
    purpose="把 claims/params/evidence 组装成符合 research.json schema 的 payload",
    tools=("read_evidence", "read_claims"),
    uses_llm=False,
)
AUDITOR = RoleSpec(
    name="auditor",
    purpose="确定性校验：schema、占位符、质量下限、语言",
    tools=("validate_document", "quality", "language"),
    uses_llm=False,
)

ROLES: dict[str, RoleSpec] = {
    spec.name: spec for spec in (EXTRACTOR, RESEARCHER, WRITER, AUDITOR)
}

EXTRACTOR_SYSTEM = (
    "你是研究流水线的抽取角色。只从给定上下文里抽取可引用的证据，不得编造 URL、"
    "不得写结论、不得改写数字。输出 JSON：{\"evidence\": [{\"quote\": str, "
    "\"url\": str|null, \"source_type\": str|null}]}，每条 quote 必须是原文片段。"
)
RESEARCHER_SYSTEM = (
    "你是研究流水线的研究角色。只能使用提供的证据列表（evidence）写 D1-D6 判断，"
    "每个 claim 必须引用已有 evidence id；没有证据就写 unknown。数字一律用 "
    "{{metric:id}} 占位符，不要写原始数字。输出 JSON：{\"claims\": [...], "
    "\"params\": [...]}，字段与 research.json 的 claims/params 一致。"
)


class ToolBox:
    """A per-role view over a fixed tool mapping."""

    def __init__(self, spec: RoleSpec, tools: Mapping[str, Callable[..., Any]]) -> None:
        self.spec = spec
        self._tools = {name: tools[name] for name in spec.tools if name in tools}

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ToolNotAllowed(name, self.spec.name)
        return self._tools[name](*args, **kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


def validate_extraction(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise RoleError("extractor output must contain a non-empty evidence list")
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, Mapping):
            raise RoleError(f"evidence #{index} must be an object")
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            raise RoleError(f"evidence #{index} is missing a quote")
        url = item.get("url") or None
        source_type = item.get("source_type") or ("web" if url else "data")
        if url is not None and not (
            isinstance(url, str) and url.startswith(("http://", "https://", "pdf://"))
        ):
            raise RoleError(f"evidence #{index} has an invalid url")
        cleaned.append(
            {
                "id": str(item.get("id") or f"ev-{index}"),
                "quote": quote.strip(),
                "url": url,
                "source_type": str(source_type),
            }
        )
    return cleaned


def validate_research_draft(payload: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    claims = payload.get("claims")
    params = payload.get("params") or []
    if not isinstance(claims, list) or not claims:
        raise RoleError("researcher output must contain a non-empty claims list")
    if not isinstance(params, list):
        raise RoleError("researcher params must be a list")
    return claims, params


def assemble_payload(
    evidence: Sequence[Mapping[str, Any]],
    claims: Sequence[Any],
    params: Sequence[Any],
) -> dict[str, Any]:
    return {"evidence": [dict(item) for item in evidence], "claims": list(claims), "params": list(params)}


def estimate_tokens(payload: Mapping[str, Any]) -> int:
    """Cheap, deterministic token proxy used for budget charging."""

    return max(1, len(json.dumps(payload, ensure_ascii=False)) // 3)
