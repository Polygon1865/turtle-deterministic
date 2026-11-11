"""Dependency-free Markdown -> HTML for deterministic research reports.

Only the constructs used by ``analysis_report.md`` are supported: headings,
paragraphs, lists, tables, blockquotes, bold, inline code and links.  The
renderer adds a reading shell (sticky table of contents, report meta, print
styles) without changing any number in the source Markdown.
"""

# ruff: noqa: E501

from __future__ import annotations

import html
import re
from pathlib import Path

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_CODE_IN_TITLE = re.compile(r"\b(\d{6}\.(?:SH|SZ|BJ)|\d{5}\.HK)\b")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    return escaped


def _cells(line: str) -> list[str]:
    """Split a table row on unescaped pipes (``\\|`` is literal text)."""

    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body) and body[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(set(cell) <= set(":- ") for cell in cells)


def _market(code: str) -> str:
    return "HK" if code.endswith(".HK") else "A"


def _toc_html(headings: list[tuple[int, str, str]]) -> str:
    links = "".join(
        f'<a class="toc-l{level}" data-panel="{_panel_for(text)}" href="#{anchor}">{html.escape(text)}</a>'
        for level, text, anchor in headings
        if level == 2
    )
    if not links:
        return ""
    return f'<nav class="toc" aria-label="目录"><div class="toc-title">目录</div>{links}</nav>'


_PANEL_LABELS = (
    ("decision", "决策"),
    ("factors", "因子"),
    ("research", "研究"),
    ("appendix", "附录"),
)
_REPORT_TABS = (
    '<nav class="report-tabs" aria-label="报告视图">'
    + "".join(
        f'<button type="button" data-panel-tab="{key}" aria-selected="false">{label}</button>'
        for key, label in _PANEL_LABELS
    )
    + "</nav>"
)
_REPORT_SCRIPT = """<script>
(function () {
  var article = document.querySelector("article.report");
  if (!article) return;
  var tabs = Array.prototype.slice.call(article.querySelectorAll("[data-panel-tab]"));
  var nodes = Array.prototype.slice.call(article.childNodes);
  var keys = ["decision", "factors", "research", "appendix"];
  var panels = {};
  keys.forEach(function (key) {
    var panel = document.createElement("div");
    panel.className = "report-panel";
    panel.setAttribute("data-panel-view", key);
    article.appendChild(panel);
    panels[key] = panel;
  });
  var anchors = Array.prototype.slice.call(article.querySelectorAll(":scope > h2[data-panel], :scope > details[data-panel]"));
  if (anchors.length < 2) {
    tabs.forEach(function (tab) { tab.hidden = true; });
    return;
  }
  var current = null;
  nodes.forEach(function (node) {
    if (node.nodeType === 1 && (node.matches("h2[data-panel]") || node.matches("details[data-panel]"))) {
      current = node.getAttribute("data-panel");
    }
    if (current && panels[current]) panels[current].appendChild(node);
  });
  function activate(key) {
    keys.forEach(function (name) {
      if (panels[name]) panels[name].classList.toggle("active", name === key);
    });
    tabs.forEach(function (tab) {
      tab.setAttribute("aria-selected", String(tab.getAttribute("data-panel-tab") === key));
    });
  }
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () { activate(tab.getAttribute("data-panel-tab")); });
  });
  Array.prototype.slice.call(document.querySelectorAll(".toc a[data-panel]")).forEach(function (link) {
    link.addEventListener("click", function (event) {
      var target = document.getElementById(link.getAttribute("href").slice(1));
      if (!target) return;
      activate(link.getAttribute("data-panel"));
      if (target.tagName === "DETAILS") target.open = true;
      window.requestAnimationFrame(function () { target.scrollIntoView({ behavior: "smooth", block: "start" }); });
      event.preventDefault();
    });
  });
  activate("decision");
  var initial = new URLSearchParams(window.location.search).get("view");
  if (initial && panels[initial]) activate(initial);
})();
</script>"""


_SECTION_NUMBER = re.compile(r"^[一二三四五六七八九十百]+、\s*")


def _panel_for(text: str) -> str:
    title = _SECTION_NUMBER.sub("", text)
    if title.startswith(("结论", "因子 4", "估值指标与底价", "投资论点卡")):
        return "decision"
    if title.startswith(("因子 1A", "因子 1B", "因子 2", "因子 3")):
        return "factors"
    if title.startswith(("行业分类", "行业模板", "研究摘要", "研究判断")):
        return "research"
    return "appendix"


_FOLD_HEADINGS = {"证据索引", "定性证据", "数字交叉验证", "研究参数"}
_FOLD_H2 = {
    "补充基本面（Tushare）",
    "市场与宏观（Tushare）",
    "来源冲突决策（SourceRank）",
    "数据问题与待验证事项",
}


def _fold_h2(text: str) -> bool:
    return any(text.endswith(name) for name in _FOLD_H2)


def _quick_read(markdown_text: str, *, has_research: bool) -> str:
    verdict = re.search(r"\*\*(买入|观察|排除|减持)\*\*\s*[—-]\s*(.+)", markdown_text)
    if verdict is None:
        return ""
    floor = re.search(r"综合底价：([\d,.]+)", markdown_text)
    premium = re.search(r"当前价溢价：([\d,.]+%)", markdown_text)
    margin = re.search(r"\|\s*安全边际\s*\|\s*([^|]+)\|", markdown_text)
    confidence = re.search(r"\|\s*外推可信度\s*\|\s*([^|]+)\|", markdown_text)
    rough = re.search(r"\|\s*粗算回报率\s*R\s*\|\s*([^|]+)\|", markdown_text)
    refined = re.search(r"\|\s*精算回报率\s*GG\s*\|\s*([^|]+)\|", markdown_text)
    threshold = re.search(r"\|\s*门槛\s*II\s*\|\s*([^|]+)\|", markdown_text)
    position = re.search(r"\|\s*仓位建议\s*\|\s*([^|]+)\|", markdown_text)
    confidence_labels = {"low": "低", "medium": "中", "high": "高"}
    confidence_value = confidence.group(1).strip() if confidence else "—"
    confidence_value = confidence_labels.get(confidence_value.lower(), confidence_value)
    cells = [
        ("综合底价", floor.group(1) if floor else "—"),
        ("当前价溢价", premium.group(1) if premium else "—"),
        ("安全边际", margin.group(1).strip() if margin else "—"),
        ("粗算 R / 精算 GG", f"{rough.group(1).strip() if rough else '—'} / {refined.group(1).strip() if refined else '—'}"),
        ("门槛 II", threshold.group(1).strip() if threshold else "—"),
        ("外推可信度", confidence_value),
    ]
    tone = "neg" if verdict.group(1) in {"排除", "减持"} else "pos"
    metrics = "".join(
        f'<div class="qr-cell"><span>{label}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in cells
    )
    source = "LLM 研究 + 确定性数字" if has_research else "确定性报告"
    position_html = (
        f'<div class="qr-position">仓位建议：{_inline(position.group(1).strip())}</div>'
        if position
        else ""
    )
    return (
        f'<section class="quickread" aria-label="决策摘要">'
        f'<div class="qr-main"><div class="qr-kicker">决策摘要 · {source}</div>'
        f'<div class="qr-verdict {tone}">{verdict.group(1)}</div>'
        f'<p>{_inline(verdict.group(2).strip())}</p>{position_html}</div>'
        f'<div class="qr-grid">{metrics}</div></section>'
    )


def markdown_to_html(
    markdown_text: str,
    *,
    title: str = "Turtle Report",
    chart_html: str = "",
    back_href: str = "/",
) -> str:
    raw_lines = markdown_text.splitlines()
    has_research = (
        re.search(r"^##\s+(?:[一二三四五六七八九十]+、\s*)?研究摘要", markdown_text, re.M)
        is not None
    ) and "**研究覆盖**" in markdown_text
    quick = _quick_read(markdown_text, has_research=has_research)
    body: list[str] = []
    headings: list[tuple[int, str, str]] = []
    display_title = title
    found_h1 = False
    paragraph: list[str] = []
    in_list = False
    in_table = False
    in_fold = False
    in_section_fold = False
    skip_table = False
    summary_table_skipped = False
    current_h2 = ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            body.append("</tbody></table></div>")
            in_table = False

    def close_fold() -> None:
        nonlocal in_fold
        if in_fold:
            body.append("</details>")
            in_fold = False

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            close_table()
            skip_table = False
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            close_list()
            if _is_separator(stripped):
                continue
            cells = _cells(stripped)
            if skip_table:
                continue
            if (
                quick
                and not in_table
                and not summary_table_skipped
                and cells[:2] == ["项目", "数值"]
            ):
                summary_table_skipped = True
                skip_table = True
                continue
            if (
                not in_table
                and current_h2.startswith("七、估值指标与底价")
                and cells[:2] == ["指标", "数值"]
            ):
                skip_table = True
                continue
            if not in_table:
                table_class = ' class="kv"' if quick and len(cells) == 2 else ""
                body.append(f'<div class="table-wrap"><table{table_class}>')
                body.append(
                    "<thead><tr>"
                    + "".join(f"<th>{_inline(c)}</th>" for c in cells)
                    + "</tr></thead><tbody>"
                )
                in_table = True
            else:
                body.append(
                    "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>"
                )
            continue

        close_table()
        if stripped.startswith("**") and stripped.endswith("**"):
            label = stripped[2:-2].strip()
            if label in _FOLD_HEADINGS or label.startswith("数字交叉验证"):
                flush_paragraph()
                close_list()
                close_fold()
                body.append(
                    f'<details class="fold"><summary>{_inline(label)} '
                    '<span class="fold-hint">展开</span></summary>'
                )
                in_fold = True
                continue

        if stripped.startswith("#"):
            flush_paragraph()
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            if level == 1 and not found_h1:
                display_title = text or title
                found_h1 = True
                continue
            if level == 2:
                current_h2 = text
                close_fold()
                in_section_fold = False
            elif not in_section_fold:
                close_fold()
            anchor = f"sec-{len(headings) + 1}"
            headings.append((level, text, anchor))
            panel = _panel_for(text) if level == 2 else ""
            panel_attr = f' data-panel="{panel}"' if panel else ""
            if level == 2 and _fold_h2(text):
                body.append(
                    f'<details class="fold section-fold" id="{anchor}"{panel_attr}><summary>'
                    f"<strong>{_inline(text)}</strong> "
                    '<span class="fold-hint">展开</span></summary>'
                )
                in_fold = True
                in_section_fold = True
                continue
            if level == 3 and text in _FOLD_HEADINGS and not in_section_fold:
                body.append(
                    f'<details class="fold"><summary>{_inline(text)} '
                    '<span class="fold-hint">展开</span></summary>'
                )
                in_fold = True
                continue
            body.append(
                f'<h{level} id="{anchor}"{panel_attr}><a class="anchor" href="#{anchor}">'
                f"{_inline(text)}</a></h{level}>"
            )
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            close_list()
            body.append(f"<blockquote>{_inline(stripped[1:].strip())}</blockquote>")
            continue

        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            item = stripped[2:]
            if item.startswith("证据："):
                continue
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(item)}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    close_table()
    close_fold()

    code = title.strip()
    match = _CODE_IN_TITLE.search(display_title) or _CODE_IN_TITLE.search(title)
    if match:
        code = match.group(1)
    market = _market(code)
    meta_label = (
        f"{market} · LLM 研究 + 确定性数字"
        if has_research
        else f"{market} · 确定性报告"
    )
    if has_research:
        lede_text = (
            "财务数字由 Python 计算并写入快照；D1–D6 研究判断由 LLM 基于冻结上下文生成，"
            "只引用指标和证据。数字仍不进入 LLM 自由生成。"
        )
        research_banner = (
            '<div class="research-banner"><span class="research-tag">LLM</span>'
            "<div><strong>本报告包含 LLM 研究判断</strong><br>"
            "第十一节 D1–D6 由 LLM 生成；结论、因子和估值中的数字仍来自确定性链路。"
            "</div></div>"
        )
    else:
        lede_text = (
            "所有财务数字由 Python 计算并写入快照；研究文本只使用指标占位符。"
            "本页可离线复现，数字不进入 LLM 自由生成。"
        )
        research_banner = ""
    chart = f'<div class="chart">{chart_html}</div>' if chart_html else ""
    toc = _toc_html(headings)
    layout_class = "layout with-toc" if toc else "layout"
    back = f'<a class="back" href="{html.escape(back_href)}">← 返回研究终端</a>' if back_href else ""

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<script>document.documentElement.classList.add("js");</script>',
            f"<title>{html.escape(display_title)} · Turtle Daily</title>",
            "<style>",
            ":root{--paper:#f3f0e8;--card:#fbf8f1;--fg:#1f1d18;--muted:#6e675b;--line:#d8d0c0;"
            "--accent:#b4552f;--soft:#ebe3d5;--warn:#8a5a1f;--warn-soft:#f3e8d6}",
            "@media (prefers-color-scheme:dark){:root{--paper:#171512;--card:#211e19;--fg:#eee9de;"
            "--muted:#a59d8e;--line:#3b352b;--accent:#e3a07d;--soft:#2b261f;--warn:#f0b27a;--warn-soft:#3b2a19}}",
            "*{box-sizing:border-box}",
            "body{margin:0;background:var(--paper);color:var(--fg);font:15px/1.75 ui-sans-serif,-apple-system,"
            "'Segoe UI','Microsoft YaHei',sans-serif}",
            "a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}",
            ".shell{max-width:1280px;margin:0 auto;padding:0 28px}",
            ".top{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:18px 0;"
            "border-bottom:1px solid var(--line);font-size:12px;color:var(--muted)}",
            ".brand{display:flex;align-items:center;gap:10px;color:var(--fg);font-weight:800;letter-spacing:-.02em}",
            ".brand .mark{width:28px;height:28px;border-radius:8px;background:var(--fg);color:var(--paper);"
            "display:grid;place-items:center;font-size:13px}",
            ".back{font-size:12px;color:var(--muted)}",
            ".hero{padding:38px 0 28px;border-bottom:1px solid var(--line)}",
            ".kicker{display:flex;gap:8px;flex-wrap:wrap;align-items:center;color:var(--muted);font-size:12px;"
            "letter-spacing:.04em;text-transform:uppercase;margin:0 0 14px}",
            ".badge{display:inline-flex;border-radius:5px;padding:2px 7px;background:var(--soft);"
            "color:var(--accent);font:700 10px/1.4 ui-monospace,monospace;letter-spacing:.06em}",
            ".hero h1{font-family:'Iowan Old Style','Palatino Linotype',Georgia,serif;"
            "font-size:clamp(30px,4vw,50px);line-height:1.08;letter-spacing:-.035em;margin:0 0 12px;"
            "max-width:900px}",
            ".lede{color:var(--muted);max-width:780px;margin:0;font-size:14px;line-height:1.65}",
            ".reading-tip{margin:14px 0 0;color:var(--muted);font-size:12px;line-height:1.6;"
            "max-width:780px;border-top:1px dashed var(--line);padding-top:10px}",
            ".research-banner{display:flex;gap:10px;align-items:flex-start;margin:18px 0 0;padding:12px 14px;"
            "border:1px solid color-mix(in srgb, var(--accent) 30%, var(--line));border-left:3px solid var(--accent);"
            "background:var(--soft);border-radius:4px;font-size:13px;color:var(--muted);max-width:780px}",
            ".research-tag{flex:0 0 auto;font:800 10px/1.6 ui-monospace,monospace;letter-spacing:.08em;"
            "color:var(--paper);background:var(--accent);border-radius:3px;padding:1px 6px}",
            ".research-banner strong{color:var(--fg)}",
            ".quickread{display:grid;grid-template-columns:1.3fr 1fr;gap:24px;margin:22px 0 0;"
            "padding:18px 20px;background:var(--card);border:1px solid var(--line);border-radius:8px;max-width:900px}",
            ".qr-kicker{font-size:10px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;"
            "color:var(--muted);margin-bottom:8px}",
            ".qr-verdict{font-family:'Iowan Old Style','Palatino Linotype',Georgia,serif;font-size:34px;"
            "font-weight:700;line-height:1;letter-spacing:-.04em;margin-bottom:6px}",
            ".qr-verdict.neg{color:var(--accent)}.qr-verdict.pos{color:var(--fg)}",
            ".qr-main p{margin:0;color:var(--muted);font-size:13px;line-height:1.55}",
            ".qr-position{margin-top:8px;font:600 11px/1.5 ui-monospace,monospace;color:var(--muted)}",
            ".qr-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;align-content:center}",
            ".qr-cell{border-top:1px solid var(--line);padding-top:8px}",
            ".qr-cell span{display:block;font-size:10px;letter-spacing:.05em;color:var(--muted)}",
            ".qr-cell strong{font:700 17px/1.4 ui-monospace,monospace;font-variant-numeric:tabular-nums}",
            ".fold{margin:14px 0;border:1px solid var(--line);border-radius:7px;background:var(--card)}",
            ".fold summary{cursor:pointer;padding:11px 14px;font-weight:700;font-size:13px;color:var(--fg)}",
            ".fold summary::marker{color:var(--accent)}",
            ".fold-hint{font-weight:400;font-size:10px;color:var(--muted);margin-left:6px}",
            ".fold[open] .fold-hint{display:none}.fold .table-wrap{border:0;border-top:1px solid var(--line)}",
            ".section-fold{margin:2.4rem 0;border:0;background:transparent}",
            ".section-fold summary{font-family:'Iowan Old Style','Palatino Linotype',Georgia,serif;"
            "font-size:24px;line-height:1.25;padding:0 0 .45rem;border-bottom:1px solid var(--line)}",
            ".section-fold .fold-hint{font-family:ui-sans-serif,sans-serif;font-size:10px}",
            ".layout{display:grid;grid-template-columns:minmax(0,1fr);gap:40px;padding:34px 0 64px}",
            ".layout.with-toc{grid-template-columns:220px minmax(0,1fr)}",
            ".toc{position:sticky;top:20px;align-self:start;max-height:calc(100vh - 40px);overflow:auto;"
            "padding:16px 14px;border:1px solid var(--line);border-radius:10px;background:var(--card)}",
            ".toc-title{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--muted);"
            "text-transform:uppercase;margin-bottom:9px}",
            ".toc a{display:block;padding:5px 0;font-size:12.5px;color:var(--muted);line-height:1.4}",
            ".toc a:hover{color:var(--accent);text-decoration:none}",
            ".toc-l2{font-weight:700;color:var(--fg)!important}.toc-l3{padding-left:12px!important}",
            ".report{min-width:0;max-width:860px}",
            ".report>h1{display:none}",
            ".report-tabs{display:none;gap:5px;flex-wrap:wrap;margin:0 0 26px;padding:0 0 12px;"
            "border-bottom:1px solid var(--line)}",
            ".js .report-tabs{display:flex}",
            ".report-tabs button{appearance:none;border:1px solid var(--line);background:var(--card);"
            "color:var(--muted);border-radius:999px;padding:6px 15px;font:700 12px/1.4 ui-sans-serif,sans-serif;"
            "letter-spacing:.02em;cursor:pointer}",
            ".report-tabs button[aria-selected='true']{background:var(--fg);color:var(--paper);border-color:var(--fg)}",
            ".report-panel{display:block}.js .report-panel{display:none}.js .report-panel.active{display:block}",
            "h2{font-family:'Iowan Old Style','Palatino Linotype',Georgia,serif;font-size:26px;line-height:1.25;"
            "letter-spacing:-.02em;margin:2.6rem 0 .85rem;padding-bottom:.45rem;border-bottom:1px solid var(--line);"
            "scroll-margin-top:18px}",
            "h3{font-size:19px;line-height:1.35;margin:1.9rem 0 .55rem;scroll-margin-top:18px}",
            "h4{font-size:15.5px;margin:1.35rem 0 .45rem}",
            ".anchor{color:inherit}.anchor:hover{text-decoration:none;color:var(--accent)}",
            "p{margin:.85rem 0;line-height:1.8}",
            "ul{padding-left:1.25rem;margin:.85rem 0}li{margin:.2rem 0}",
            ".table-wrap{overflow-x:auto;margin:1.15rem 0;border:1px solid var(--line);border-radius:8px;"
            "background:var(--card)}",
            "table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:560px;"
            "font-variant-numeric:tabular-nums}",
            ".table-wrap table.kv{min-width:0}.table-wrap table.kv td:first-child{width:38%;color:var(--muted)}",
            "th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top;"
            "line-height:1.55}",
            "th{position:sticky;top:0;z-index:1;background:var(--soft);font-size:11.5px;letter-spacing:.02em;"
            "color:var(--muted);font-weight:800;white-space:nowrap}",
            "tbody tr:nth-child(even){background:color-mix(in srgb,var(--soft) 38%,transparent)}",
            "tr:last-child td{border-bottom:0}",
            "blockquote{margin:1.1rem 0;padding:11px 15px;border-left:3px solid var(--accent);"
            "background:var(--soft);border-radius:0 6px 6px 0;color:var(--muted);font-size:13.5px;line-height:1.7}",
            "code{font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;background:var(--soft);"
            "padding:2px 5px;border-radius:4px}",
            ".chart{margin:1rem 0 1.5rem}.chart svg{width:100%;height:auto;border:1px solid var(--line);"
            "border-radius:10px;background:var(--card)}",
            ".footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;color:var(--muted);"
            "font-size:11px;padding:18px 0 36px;border-top:1px solid var(--line)}",
            "@media(max-width:900px){.layout.with-toc{grid-template-columns:1fr}.toc{display:none}"
            ".quickread{grid-template-columns:1fr}}",
            "@media(max-width:640px){.shell{padding:0 16px}.hero{padding-top:24px}"
            ".top{font-size:11px}.hero h1{font-size:29px}.report{max-width:none}"
            "body{font-size:14.5px}.reading-tip{font-size:11px}table{font-size:12.5px}"
            "th,td{padding:8px 9px}.quickread{padding:15px}.qr-grid{grid-template-columns:1fr 1fr}"
            ".report-tabs{flex-wrap:nowrap;overflow-x:auto;padding-bottom:10px}}",
            "@media print{.top,.toc,.back{display:none}.layout{display:block;padding:0}"
            "body{background:#fff;color:#000;font-size:10.5pt}.table-wrap{overflow:visible}"
            "h2{break-after:avoid;page-break-after:avoid}table{font-size:9pt}"
            "thead{display:table-header-group}tr{break-inside:avoid;page-break-inside:avoid}}",
            "</style></head><body>",
            '<div class="shell">',
            '<header class="top"><a class="brand" href="/"><span class="mark">T</span>Turtle Daily</a>'
            f"{back}</header>",
            '<section class="hero"><div class="kicker">'
            f'<span class="badge">{html.escape(code)}</span><span>{html.escape(meta_label)}</span>'
            f'<span>· {"研究判断由 LLM 生成" if has_research else "数字来自确定性指标与已冻结事实"}</span></div>'
            f"<h1>{_inline(display_title)}</h1>"
            f'<p class="lede">{lede_text}</p>'
            '<p class="reading-tip">建议阅读顺序：结论 → 因子 4 → 估值与底价 → 数据问题。'
            "左侧目录可跳转，表格可横向滚动。</p>"
            f"{research_banner}{quick}</section>",
            f'<div class="{layout_class}">',
            toc,
            f'<article class="report">{chart}{_REPORT_TABS}',
            *body,
            "</article></div>",
            '<footer class="footer"><span>Generated by turtle-framework · deterministic numbers</span>'
            f"<span>{html.escape(code)} · 仅供研究，不构成投资建议</span></footer>",
            _REPORT_SCRIPT,
            "</div></body></html>",
        ]
    )


def convert_file(
    input_path: Path | str,
    output_path: Path | str,
    *,
    title: str = "Turtle Report",
    chart_html: str | None = None,
    back_href: str = "/",
) -> Path:
    source = Path(input_path)
    target = Path(output_path)
    if chart_html is None:
        from .charts import chart_for

        chart_html = chart_for(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        markdown_to_html(
            source.read_text(encoding="utf-8"),
            title=title,
            chart_html=chart_html,
            back_href=back_href,
        ),
        encoding="utf-8",
    )
    return target
