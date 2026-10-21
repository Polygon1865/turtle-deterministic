"""Dependency-free SVG charts for the HTML report.

Charts are presentation only: they reuse the frozen price history and the
valuation metrics already stored next to ``analysis_report.md``.  They never
feed numbers back into the report or the valuation.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

_MAX_POINTS = 240
_WIDTH = 900
_HEIGHT = 280


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _metric_value(metrics: Mapping[str, object], key: str) -> Decimal | None:
    item = metrics.get(key)
    if not isinstance(item, Mapping):
        return None
    return _decimal(item.get("value"))


def price_chart(
    history: Sequence[Mapping[str, object]],
    *,
    price: Decimal | None = None,
    floor: Decimal | None = None,
    width: int = _WIDTH,
    height: int = _HEIGHT,
    max_points: int = _MAX_POINTS,
) -> str:
    points: list[tuple[str, Decimal]] = []
    for row in history[-max_points:]:
        close = _decimal(row.get("close"))
        date = str(row.get("trade_date") or "")
        if close is None or close <= 0 or not date:
            continue
        points.append((date, close))
    if len(points) < 2:
        return ""

    values = [value for _, value in points]
    for marker in (price, floor):
        if marker is not None and marker > 0:
            values.append(marker)
    low, high = min(values), max(values)
    if high <= low:
        high = low + Decimal(1)

    left, right, top, bottom = 56, width - 18, 28, height - 38
    plot_width = right - left
    plot_height = bottom - top

    def x_at(index: int) -> Decimal:
        return Decimal(left) + Decimal(plot_width) * Decimal(index) / Decimal(len(points) - 1)

    def y_at(value: Decimal) -> Decimal:
        return Decimal(bottom) - (value - low) / (high - low) * Decimal(plot_height)

    polyline = " ".join(f"{x_at(i):.1f},{y_at(value):.1f}" for i, (_, value) in enumerate(points))
    parts = [
        f'<figure class="chart"><svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="股价走势与估值底价">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#d0d7de"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#d0d7de"/>',
        f'<text x="{left}" y="18" font-size="13" fill="#57606a">收盘价（最近 {len(points)} 个交易日）</text>',
        f'<polyline fill="none" stroke="#0969da" stroke-width="2" points="{polyline}"/>',
    ]
    for marker, colour, label, dash in (
        (price, "#0969da", "当前价", ""),
        (floor, "#bf8700", "综合底价", ' stroke-dasharray="6 4"'),
    ):
        if marker is None or marker <= 0:
            continue
        y = y_at(marker)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
            f'stroke="{colour}" stroke-width="1.4"{dash}/>'
        )
        parts.append(
            f'<text x="{left + 6}" y="{y - 5:.1f}" font-size="12" fill="{colour}">'
            f"{html.escape(label)} {marker:.2f}</text>"
        )
    parts.append(
        f'<text x="{left}" y="{height - 12}" font-size="11" fill="#8c959f">'
        f"{html.escape(points[0][0])}</text>"
    )
    parts.append(
        f'<text x="{right - 70}" y="{height - 12}" font-size="11" fill="#8c959f">'
        f"{html.escape(points[-1][0])}</text>"
    )
    parts.append("</svg></figure>")
    return "".join(parts)


def chart_for(source: Path | str) -> str:
    """Build a price chart when the report has sibling snapshot files."""
    path = Path(source)
    inputs_path = path.with_name("inputs.json")
    metrics_path = path.with_name("metrics.json")
    if not inputs_path.is_file() or not metrics_path.is_file():
        return ""
    try:
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(inputs, Mapping) or not isinstance(metrics, Mapping):
        return ""
    history = inputs.get("history")
    if not isinstance(history, list):
        return ""
    return price_chart(
        [row for row in history if isinstance(row, Mapping)],
        price=_metric_value(metrics, "price"),
        floor=_metric_value(metrics, "floor"),
    )
