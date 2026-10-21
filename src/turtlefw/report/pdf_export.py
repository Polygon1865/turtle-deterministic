"""Optional HTML-to-PDF export through an installed Chromium browser.

The project keeps its runtime dependencies small; PDF export therefore uses
Edge/Chrome in headless mode when available and fails with an actionable error
otherwise.  The HTML itself is generated deterministically by ``report.html``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_CANDIDATES = (
    "msedge",
    "microsoft-edge",
    "chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
_WINDOWS_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def find_browser() -> str | None:
    """Return an explicit browser path, ``$TURTLE_BROWSER``, or a PATH match."""
    override = os.environ.get("TURTLE_BROWSER", "").strip()
    if override:
        return override
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for candidate in _WINDOWS_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def build_command(browser: str, html_path: Path, pdf_path: Path) -> list[str]:
    """Pure command builder, kept separate so it can be unit tested."""
    return [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}",
        html_path.resolve().as_uri(),
    ]


def html_to_pdf(
    html_path: str | Path,
    pdf_path: str | Path,
    *,
    browser: str | None = None,
    timeout: int = 90,
) -> Path:
    """Render ``html_path`` to ``pdf_path``; raise ``RuntimeError`` on failure."""
    source = Path(html_path)
    target = Path(pdf_path)
    if not source.is_file():
        raise RuntimeError(f"HTML 输入不存在：{source}")
    executable = browser or find_browser()
    if not executable:
        raise RuntimeError(
            "未找到 Edge/Chrome，无法导出 PDF；可设置 TURTLE_BROWSER 指向浏览器可执行文件"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        build_command(executable, source, target),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"PDF 导出失败（exit {completed.returncode}）：{detail[:400]}")
    return target
