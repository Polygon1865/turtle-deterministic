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
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(set(cell) <= set(":- ") for cell in cells)


def _market(code: str) -> str:
    return "HK" if code.endswith(".HK") else "A"


def _toc_html(headings: list[tuple[int, str, str]]) -> str:
    links = "".join(
        f'<a class="toc-l{level}" href="#{anchor}">{html.escape(text)}</a>'
        for level, text, anchor in headings
        if level in (2, 3)
    )
    if not links:
        return ""
    return f'<nav class="toc" aria-label="目录"><div class="toc-title">目录</div>{links}</nav>'


def markdown_to_html(
    markdown_text: str,
    *,
    title: str = "Turtle Report",
    chart_html: str = "",
    back_href: str = "/",
) -> str:
    raw_lines = markdown_text.splitlines()
    body: list[str] = []
    headings: list[tuple[int, str, str]] = []
    display_title = title
    found_h1 = False
    paragraph: list[str] = []
    in_list = False
    in_table = False

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

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            close_table()
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            close_list()
            if _is_separator(stripped):
                continue
            cells = _cells(stripped)
            if not in_table:
                body.append('<div class="table-wrap"><table>')
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
        if stripped.startswith("#"):
            flush_paragraph()
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            if level == 1 and not found_h1:
                display_title = text or title
                found_h1 = True
                continue
            anchor = f"sec-{len(headings) + 1}"
            headings.append((level, text, anchor))
            body.append(
                f'<h{level} id="{anchor}"><a class="anchor" href="#{anchor}">'
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
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(stripped[2:])}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    close_table()

    code = title.strip()
    match = _CODE_IN_TITLE.search(display_title) or _CODE_IN_TITLE.search(title)
    if match:
        code = match.group(1)
    market = _market(code)
    meta_label = f"{market} · 确定性报告"
    chart = f'<div class="chart">{chart_html}</div>' if chart_html else ""
    toc = _toc_html(headings)
    layout_class = "layout with-toc" if toc else "layout"
    back = f'<a class="back" href="{html.escape(back_href)}">← 返回研究终端</a>' if back_href else ""

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(display_title)} · Turtle Daily</title>",
            "<style>",
            ":root{--paper:#f7f5f1;--card:#fffdf9;--fg:#14201d;--muted:#66736e;--line:#dedbd3;"
            "--accent:#0f4d3f;--soft:#e7f0eb;--warn:#9a3412;--warn-soft:#ffedd5}",
            "@media (prefers-color-scheme:dark){:root{--paper:#101614;--card:#151d1a;--fg:#e8eee9;"
            "--muted:#9aa8a2;--line:#2a3631;--accent:#8fd3b8;--soft:#1b2a24;--warn:#fdba74;--warn-soft:#3a2114}}",
            "*{box-sizing:border-box}",
            "body{margin:0;background:var(--paper);color:var(--fg);font:15px/1.7 system-ui,-apple-system,"
            "'Segoe UI','Microsoft YaHei',sans-serif}",
            "a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}",
            ".shell{max-width:1240px;margin:0 auto;padding:0 28px}",
            ".top{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:18px 0;"
            "border-bottom:1px solid var(--line);font-size:12px;color:var(--muted)}",
            ".brand{display:flex;align-items:center;gap:10px;color:var(--fg);font-weight:800;letter-spacing:-.02em}",
            ".brand .mark{width:28px;height:28px;border-radius:8px;background:var(--fg);color:var(--paper);"
            "display:grid;place-items:center;font-size:13px}",
            ".back{font-size:12px;color:var(--muted)}",
            ".hero{padding:34px 0 24px;border-bottom:1px solid var(--line)}",
            ".kicker{display:flex;gap:8px;flex-wrap:wrap;align-items:center;color:var(--muted);font-size:12px;"
            "letter-spacing:.04em;text-transform:uppercase;margin:0 0 14px}",
            ".badge{display:inline-flex;border-radius:5px;padding:2px 7px;background:var(--soft);"
            "color:var(--accent);font:700 10px/1.4 ui-monospace,monospace;letter-spacing:.06em}",
            ".hero h1{font-size:clamp(28px,4vw,46px);line-height:1.12;letter-spacing:-.035em;margin:0 0 12px;"
            "max-width:900px}",
            ".lede{color:var(--muted);max-width:780px;margin:0;font-size:14px}",
            ".layout{display:grid;grid-template-columns:minmax(0,1fr);gap:36px;padding:30px 0 56px}",
            ".layout.with-toc{grid-template-columns:210px minmax(0,1fr)}",
            ".toc{position:sticky;top:20px;align-self:start;max-height:calc(100vh - 40px);overflow:auto;"
            "padding:16px 14px;border:1px solid var(--line);border-radius:12px;background:var(--card)}",
            ".toc-title{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--muted);"
            "text-transform:uppercase;margin-bottom:8px}",
            ".toc a{display:block;padding:5px 0;font-size:12px;color:var(--muted);line-height:1.35}",
            ".toc a:hover{color:var(--accent);text-decoration:none}",
            ".toc-l2{font-weight:700;color:var(--fg)!important}.toc-l3{padding-left:12px!important}",
            ".report{min-width:0;max-width:900px}",
            ".report>h1{display:none}",
            "h2{font-size:24px;line-height:1.25;letter-spacing:-.02em;margin:2.2rem 0 .8rem;"
            "padding-bottom:.45rem;border-bottom:1px solid var(--line)}",
            "h3{font-size:18px;line-height:1.3;margin:1.7rem 0 .5rem}",
            "h4{font-size:15px;margin:1.2rem 0 .4rem}",
            ".anchor{color:inherit}.anchor:hover{text-decoration:none;color:var(--accent)}",
            "p{margin:.7rem 0}",
            "ul{padding-left:1.2rem;margin:.7rem 0}",
            ".table-wrap{overflow-x:auto;margin:1rem 0;border:1px solid var(--line);border-radius:10px;"
            "background:var(--card)}",
            "table{border-collapse:collapse;width:100%;font-size:13px;min-width:560px}",
            "th,td{border-bottom:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}",
            "th{background:var(--soft);font-size:11px;letter-spacing:.02em;color:var(--muted);"
            "font-weight:800;white-space:nowrap}",
            "tr:last-child td{border-bottom:0}",
            "blockquote{margin:1rem 0;padding:10px 14px;border-left:3px solid var(--accent);"
            "background:var(--soft);border-radius:0 8px 8px 0;color:var(--muted);font-size:13px}",
            "code{font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;background:var(--soft);"
            "padding:2px 5px;border-radius:4px}",
            ".chart{margin:1rem 0 1.5rem}.chart svg{width:100%;height:auto;border:1px solid var(--line);"
            "border-radius:10px;background:var(--card)}",
            ".footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;color:var(--muted);"
            "font-size:11px;padding:18px 0 36px;border-top:1px solid var(--line)}",
            "@media(max-width:900px){.layout.with-toc{grid-template-columns:1fr}.toc{position:static;"
            "max-height:none;display:flex;flex-wrap:wrap;gap:4px 14px}.toc-title{width:100%}"
            ".toc a{padding:3px 0}.toc-l3{display:none}}",
            "@media(max-width:640px){.shell{padding:0 16px}.hero{padding-top:22px}"
            ".top{font-size:11px}.hero h1{font-size:30px}.report{max-width:none}}",
            "@media print{.top,.toc,.back{display:none}.layout{display:block;padding:0}"
            "body{background:#fff;color:#000}.table-wrap{overflow:visible}}",
            "</style></head><body>",
            '<div class="shell">',
            '<header class="top"><a class="brand" href="/"><span class="mark">T</span>Turtle Daily</a>'
            f"{back}</header>",
            '<section class="hero"><div class="kicker">'
            f'<span class="badge">{html.escape(code)}</span><span>{html.escape(meta_label)}</span>'
            '<span>· 数字来自确定性指标与已冻结事实</span></div>'
            f"<h1>{_inline(display_title)}</h1>"
            '<p class="lede">所有财务数字由 Python 计算并写入快照；研究文本只使用指标占位符。'
            "本页可离线复现，数字不进入 LLM 自由生成。</p></section>",
            f'<div class="{layout_class}">',
            toc,
            f'<article class="report">{chart}',
            *body,
            "</article></div>",
            '<footer class="footer"><span>Generated by turtle-framework · deterministic report</span>'
            f"<span>{html.escape(code)} · 仅供研究，不构成投资建议</span></footer>",
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
