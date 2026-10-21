from __future__ import annotations

from pathlib import Path

import pytest

from turtlefw.report.pdf_export import build_command, find_browser, html_to_pdf


def test_build_command_uses_file_uri(tmp_path: Path) -> None:
    html = tmp_path / "report.html"
    pdf = tmp_path / "report.pdf"
    command = build_command("edge", html, pdf)
    assert command[0] == "edge"
    assert "--headless=new" in command
    assert f"--print-to-pdf={pdf.resolve()}" in command
    assert command[-1] == html.resolve().as_uri()


def test_find_browser_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURTLE_BROWSER", "C:/fake/browser.exe")
    assert find_browser() == "C:/fake/browser.exe"


def test_html_to_pdf_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="HTML 输入不存在"):
        html_to_pdf(tmp_path / "missing.html", tmp_path / "out.pdf")
