"""Daily production pipeline for a single Windows host.

The pipeline is deliberately thin: it orchestrates the existing deterministic
CLI and never computes report numbers itself.  A run is considered successful
only when every selected stock produced a passing QA artifact and a published
site release.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

_ROW_CODE_KEYS = ("ts_code", "code", "symbol")
_DATE_RE = re.compile(r"交易日[：:]\s*(\d{8})")
_SAFE_CODE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")


def _validate_code(code: str) -> str:
    text = code.strip()
    if not text or ".." in text or not _SAFE_CODE_RE.fullmatch(text):
        raise DailyError(f"invalid stock code: {code!r}")
    return text


class DailyError(RuntimeError):
    """Raised when the daily pipeline cannot continue safely."""


HK_DEFAULT_CODES: tuple[str, ...] = (
    "00700.HK",
    "09988.HK",
    "03690.HK",
    "01810.HK",
    "00941.HK",
    "01024.HK",
    "02318.HK",
    "02382.HK",
    "00388.HK",
    "09618.HK",
    "00883.HK",
    "00939.HK",
    "01398.HK",
    "03988.HK",
    "02628.HK",
    "02388.HK",
    "00016.HK",
    "00001.HK",
    "02020.HK",
    "01211.HK",
)
HK_DEFAULT_NAMES: dict[str, str] = {
    "00700.HK": "腾讯控股",
    "09988.HK": "阿里巴巴-W",
    "03690.HK": "美团-W",
    "01810.HK": "小米集团-W",
    "00941.HK": "中国移动",
    "01024.HK": "快手-W",
    "02318.HK": "中国平安",
    "02382.HK": "舜宇光学科技",
    "00388.HK": "香港交易所",
    "09618.HK": "京东集团-SW",
    "00883.HK": "中国海洋石油",
    "00939.HK": "建设银行",
    "01398.HK": "工商银行",
    "03988.HK": "中国银行",
    "02628.HK": "中国人寿",
    "02388.HK": "中银香港",
    "00016.HK": "新鸿基地产",
    "00001.HK": "长和",
    "02020.HK": "安踏体育",
    "01211.HK": "比亚迪股份",
}


@dataclass(frozen=True)
class DailyConfig:
    top_n: int = 20
    llm_top_n: int = 0
    fast_limit: int = 100
    deep_limit: int = 30
    markets: tuple[str, ...] = ("A",)
    hk_codes: tuple[str, ...] = ()
    hk_limit: int = 20
    hk_candidate_limit: int = 100
    hk_llm_top_n: int = 3
    rf: str | None = None
    rf_source: str = ""
    research_max_input_tokens: int = 60_000
    research_retries: int = 1
    screen_attempts: int = 3
    retry_seconds: int = 1_800
    workers: int = 1
    report_workers: int = 1
    api_interval: float = 0.35
    stock_timeout_seconds: int = 1_800
    screen_timeout_seconds: int = 1_800
    refresh_market: bool = True
    allow_stale: bool = False
    publish_partial: bool = True
    resume: bool = False
    project_root: str = "."


@dataclass(frozen=True)
class DailyPaths:
    day: date
    runs_root: Path
    site_root: Path
    pdf_root: Path

    @property
    def day_dir(self) -> Path:
        return self.runs_root / self.day.isoformat()

    @property
    def status_path(self) -> Path:
        return self.day_dir / "status.json"

    @property
    def lock_path(self) -> Path:
        return self.day_dir / ".daily.lock"


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


CommandRunner = Callable[[Sequence[str], Path, int], CommandResult]


def _command_text(command: Sequence[str]) -> str:
    return " ".join(command)


def _tail(text: str, limit: int = 2_000) -> str:
    text = text.strip()
    return text[-limit:] if len(text) > limit else text


def _clear_research_outputs(code_dir: Path) -> None:
    for base in (code_dir, code_dir / "snapshot"):
        for path in base.glob("research*.json"):
            path.unlink(missing_ok=True)


def _append_log(path: Path, title: str, result: CommandResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {title}\n$ {_command_text(result.command)}\n")
        handle.write(f"exit={result.returncode}\n")
        if result.stdout:
            handle.write("--- stdout ---\n")
            handle.write(result.stdout)
            if not result.stdout.endswith("\n"):
                handle.write("\n")
        if result.stderr:
            handle.write("--- stderr ---\n")
            handle.write(result.stderr)
            if not result.stderr.endswith("\n"):
                handle.write("\n")


def _run_process(command: Sequence[str], cwd: Path, timeout: int) -> CommandResult:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    try:
        process = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout
        if isinstance(raw_stdout, bytes):
            stdout_text = raw_stdout.decode("utf-8", errors="replace")
        else:
            stdout_text = raw_stdout or ""
        return CommandResult(
            tuple(command),
            returncode=124,
            stdout=stdout_text,
            stderr=f"timeout after {timeout}s",
        )
    except OSError as exc:
        return CommandResult(tuple(command), returncode=127, stderr=str(exc))
    return CommandResult(
        tuple(command),
        returncode=process.returncode,
        stdout=process.stdout or "",
        stderr=process.stderr or "",
    )


def _python_command(day_dir: Path, *args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "turtlefw.cli",
        "--output-dir",
        str(day_dir),
        *args,
    ]


def _project_python() -> list[str]:
    return [sys.executable, "-m", "turtlefw.cli"]


def _news_code_key(row: dict[str, str]) -> str | None:
    for key in _ROW_CODE_KEYS:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _ranking_names(path: Path) -> dict[str, str]:
    """Best-effort code→name map for a manually supplied code list."""
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.DictReader(handle)
            return {
                str(row.get("code") or row.get("ts_code") or ""): str(
                    row.get("name") or ""
                )
                for row in rows
                if (row.get("code") or row.get("ts_code"))
            }
    except (OSError, csv.Error):
        return {}


def parse_ranking(path: Path, *, limit: int) -> list[dict[str, str]]:
    """Read a screen ranking CSV and return unique codes in rank order."""

    if limit <= 0:
        raise DailyError("top_n must be positive")
    if not path.is_file():
        raise DailyError(f"ranking file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise DailyError(f"ranking file is empty: {path}")

    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        code = _news_code_key(row)
        if not code or code in seen:
            continue
        if "verdict" in row:
            verdict = str(row.get("verdict") or "").strip()
            if not verdict or "失败" in verdict:
                continue
        code = _validate_code(code)
        seen.add(code)
        selected.append(
            {
                "code": code,
                "name": str(row.get("name") or "").strip(),
                "rank": str(len(selected) + 1),
            }
        )
        if len(selected) >= limit:
            break
    if not selected:
        raise DailyError(f"ranking file has no stock codes: {path}")
    return selected


def extract_trade_date(stdout: str) -> str | None:
    match = _DATE_RE.search(stdout)
    return match.group(1) if match else None


def expected_trade_date(day: date) -> str:
    return day.strftime("%Y%m%d")


def build_screen_command(paths: DailyPaths, config: DailyConfig) -> list[str]:
    day_dir = paths.day_dir
    command = _python_command(day_dir, "screen")
    if config.refresh_market:
        command = [
            sys.executable,
            "-m",
            "turtlefw.cli",
            "--output-dir",
            str(day_dir),
            "--refresh-market",
            "screen",
        ]
    command.extend(
        [
            "--fast",
            "--fast-limit",
            str(config.fast_limit),
            "--deep",
            str(config.deep_limit),
            "--csv",
            str(day_dir / "ranking.csv"),
            "--workers",
            str(config.workers),
            "--api-interval",
            str(config.api_interval),
        ]
    )
    return command


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def qa_status(path: Path) -> str:
    """Return PASS/WARN/FAIL/UNKNOWN from a qa.json artifact."""

    payload = _read_json(path)
    if payload is None:
        return "UNKNOWN"
    status = str(payload.get("status") or "").strip().lower()
    if status in {"pass", "ok", "success"}:
        return "PASS"
    if status in {"warn", "warning"}:
        return "WARN"
    if status in {"fail", "failed", "error"}:
        return "FAIL"
    rows = payload.get("rows")
    if isinstance(rows, list):
        statuses = {
            str(row.get("status") or "").strip().upper()
            for row in rows
            if isinstance(row, dict)
        }
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        if statuses and statuses <= {"PASS", "SKIP", "OK"}:
            return "PASS"
    return "UNKNOWN"


def _manifest_summary(path: Path) -> tuple[str, str]:
    payload = _read_json(path) or {}
    return (
        str(payload.get("snapshot_id") or ""),
        str(payload.get("numeric_coverage") or ""),
    )


def _latest_pdf(pdf_root: Path, code: str) -> Path | None:
    directory = pdf_root / code
    if not directory.is_dir():
        return None
    candidates = sorted(
        (path for path in directory.glob("*.pdf") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return candidates[0] if candidates else None


@contextmanager
def daily_lock(path: Path, *, stale_after_seconds: int = 6 * 3600) -> Iterator[None]:
    """Prevent two scheduled runs from writing the same day directory.

    A crashed run leaves a lock file behind; locks older than the threshold are
    treated as stale and reclaimed once.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as exc:
            age = 0.0
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                pass
            if attempt == 0 and age > stale_after_seconds:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            raise DailyError(f"another daily run is active: {path}") from exc
    else:
        raise DailyError(f"could not acquire daily lock: {path}")

    try:
        os.write(descriptor, f"pid={os.getpid()} started={datetime.now().isoformat()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _archive_attempt(paths: DailyPaths, status: dict[str, Any]) -> None:
    attempt_id = str(status.get("attempt_id") or "")
    if not attempt_id or not paths.status_path.is_file():
        return
    attempt_dir = paths.day_dir / "attempts" / attempt_id
    try:
        attempt_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths.status_path, attempt_dir / "status.json")
    except OSError:
        return


def _notify(config: DailyConfig, payload: dict[str, Any]) -> None:
    webhook = os.environ.get("TURTLE_NOTIFY_WEBHOOK", "").strip()
    if not webhook:
        return
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except (OSError, urllib.error.URLError):
        # Notification failure must never invalidate a completed pipeline.
        return


def classify_research_failure(text: str) -> str:
    """Map an LLM/finalize error to a stable, displayable reason code."""

    lowered = text.lower()
    if "not valid json" in lowered or "json output" in lowered:
        return "json_invalid"
    if "unresolved placeholder" in lowered or "unresolved metric" in lowered:
        return "placeholder"
    if "numeric gate" in lowered or "coverage" in lowered:
        return "numeric_gate"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "language" in lowered or "simplified chinese" in lowered:
        return "language"
    if "provenance" in lowered:
        return "provenance"
    if "quality" in lowered or "claims" in lowered:
        return "quality"
    if "api key" in lowered or "model" in lowered or "http" in lowered or "llm" in lowered:
        return "llm_error"
    return "research_error"


def _preserve_failed_research(code_dir: Path, error: str, reason: str) -> Path:
    """Keep failed LLM artifacts before the deterministic fallback deletes them."""

    target = code_dir / "research_failed"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for relative in (
        "research.json",
        "research.usage.json",
        "research_audit.json",
        "research_provenance.json",
        "snapshot/research.json",
        "snapshot/research.usage.json",
        "snapshot/research_audit.json",
    ):
        source = code_dir / relative
        if not source.is_file():
            continue
        destination = target / relative.replace("/", "_")
        shutil.copyfile(source, destination)
        copied.append(str(destination))
    payload = {
        "reason": reason,
        "error": error,
        "files": copied,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }
    (target / "failure.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def run_stock(
    code: str,
    rank: int,
    paths: DailyPaths,
    config: DailyConfig,
    *,
    run_command: CommandRunner = _run_process,
    market: str = "A",
    research_rank: int | None = None,
) -> dict[str, Any]:
    """Run one stock and return a serializable status record."""

    started = time.monotonic()
    code = _validate_code(code)
    market = "HK" if market.upper() == "HK" or code.endswith(".HK") else "A"
    research_rank = rank if research_rank is None else research_rank
    code_dir = paths.day_dir / code
    code_dir.mkdir(parents=True, exist_ok=True)
    _clear_research_outputs(code_dir)
    log_path = code_dir / "pipeline.log"
    record: dict[str, Any] = {
        "code": code,
        "name": "",
        "market": market,
        "rank": rank,
        "status": "failed",
        "qa": "UNKNOWN",
        "research": "off",
        "research_reason": "",
        "research_reason_code": "",
        "research_error": "",
        "research_failed": "",
        "pdf": "none",
        "pdf_error": "",
        "snapshot_id": "",
        "numeric_coverage": "",
        "elapsed_seconds": 0.0,
        "error": "",
    }

    pdf = _latest_pdf(paths.pdf_root, code)
    pdf_index = code_dir / "pdf_index.json"
    if pdf is not None:
        pdf_command = [
            *_project_python(),
            "pdf-index",
            "--pdf",
            str(pdf),
            "--output",
            str(pdf_index),
        ]
        pdf_result = run_command(
            pdf_command, Path(config.project_root), config.stock_timeout_seconds
        )
        _append_log(log_path, "pdf-index", pdf_result)
        if pdf_result.ok and pdf_index.is_file():
            record["pdf"] = "ok"
        else:
            record["pdf"] = "error"
            record["pdf_error"] = _tail(pdf_result.stderr or pdf_result.stdout)

    wants_research = (
        research_rank <= config.hk_llm_top_n
        if market == "HK"
        else rank <= config.llm_top_n
    )

    def command(with_research: bool, note: str = "") -> list[str]:
        args = _python_command(paths.day_dir, "run", code, "--strict")
        if config.rf:
            args.extend(["--rf", config.rf])
        if config.rf_source:
            args.extend(["--rf-source", config.rf_source])
        if record["pdf"] == "ok" and pdf_index.is_file():
            args.extend(["--pdf-index", str(pdf_index)])
        if with_research:
            args.extend(
                [
                    "--with-research",
                    "--research-max-input-tokens",
                    str(config.research_max_input_tokens),
                    "--research-retries",
                    str(config.research_retries),
                ]
            )
        elif note:
            args.extend(["--research-note", note])
        return args

    result = run_command(
        command(wants_research), Path(config.project_root), config.stock_timeout_seconds
    )
    _append_log(log_path, "run", result)
    if wants_research and not result.ok:
        error = _tail(result.stderr or result.stdout)
        reason = classify_research_failure(error)
        record["research"] = "fallback"
        record["research_reason_code"] = reason
        record["research_reason"] = (
            f"LLM 研究未采用（{reason}），已回退确定性报告"
        )
        record["research_error"] = error
        failed_dir = _preserve_failed_research(code_dir, error, reason)
        record["research_failed"] = str(failed_dir)
        _clear_research_outputs(code_dir)
        result = run_command(
            command(False, record["research_reason"]),
            Path(config.project_root),
            config.stock_timeout_seconds,
        )
        _append_log(log_path, "run-fallback", result)
    elif wants_research:
        record["research"] = "on"

    qa_path = code_dir / "qa.json"
    manifest_path = code_dir / "snapshot" / "manifest.json"
    record["qa"] = qa_status(qa_path)
    record["snapshot_id"], record["numeric_coverage"] = _manifest_summary(manifest_path)
    record["elapsed_seconds"] = round(time.monotonic() - started, 2)
    for usage_path in (
        code_dir / "research.usage.json",
        code_dir / "snapshot" / "research.usage.json",
    ):
        if not usage_path.is_file():
            continue
        try:
            usage = json.loads(usage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(usage, dict):
            record["research_usage"] = usage
        break
    if result.returncode != 0:
        record["error"] = _tail(result.stderr or result.stdout)
    elif record["qa"] == "FAIL":
        record["error"] = "QA failed"
    elif record["qa"] == "UNKNOWN" and not qa_path.is_file():
        record["error"] = "qa.json missing"
    elif not (code_dir / "analysis_report.html").is_file():
        record["error"] = "analysis_report.html missing"

    if result.ok and record["qa"] in {"PASS", "WARN"} and not record["error"]:
        record["status"] = "ok"
    return record


def _hk_ranking(config: DailyConfig) -> list[dict[str, str]]:
    """Return a manually configured HK watchlist in display order."""

    codes = tuple(dict.fromkeys(_validate_code(code) for code in config.hk_codes))
    return [
        {
            "code": code,
            "name": HK_DEFAULT_NAMES.get(code, ""),
            "market": "HK",
        }
        for code in codes[: config.hk_limit]
    ]


def build_hk_screen_command(
    paths: DailyPaths, config: DailyConfig, trade_date: str
) -> list[str]:
    command = _python_command(
        paths.day_dir,
        *(["--refresh-market"] if config.refresh_market else []),
        "screen",
    )
    command.extend(
        [
            "--market",
            "HK",
            "--fast",
            "--fast-limit",
            str(config.hk_candidate_limit),
            "--api-interval",
            str(config.api_interval),
            "--csv",
            str(paths.day_dir / "ranking_hk.csv"),
        ]
    )
    if trade_date:
        command.extend(["--as-of", trade_date])
    return command


def _screen_hk(
    paths: DailyPaths,
    config: DailyConfig,
    trade_date: str,
    *,
    run_command: CommandRunner,
) -> tuple[bool, str, list[dict[str, str]]]:
    paths.day_dir.mkdir(parents=True, exist_ok=True)
    result = run_command(
        build_hk_screen_command(paths, config, trade_date),
        Path(config.project_root),
        config.screen_timeout_seconds,
    )
    if not result.ok:
        return False, _tail(result.stderr or result.stdout), []
    parsed_date = extract_trade_date(result.stdout) or trade_date
    if trade_date and parsed_date != trade_date and not config.allow_stale:
        return False, f"HK screen did not reach trade date {trade_date}", []
    try:
        rows = parse_ranking(
            paths.day_dir / "ranking_hk.csv", limit=config.hk_candidate_limit
        )
    except DailyError as exc:
        return False, str(exc), []
    for row in rows:
        row["market"] = "HK"
    return True, parsed_date, rows


def _screen(
    paths: DailyPaths,
    config: DailyConfig,
    *,
    run_command: CommandRunner,
    sleep: Callable[[float], None],
) -> tuple[bool, str, list[dict[str, str]]]:
    paths.day_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.day_dir / "screen.log"
    expected = expected_trade_date(paths.day)
    for attempt in range(1, config.screen_attempts + 1):
        result = run_command(
            build_screen_command(paths, config),
            Path(config.project_root),
            config.screen_timeout_seconds,
        )
        _append_log(log_path, f"screen attempt {attempt}", result)
        if not result.ok:
            return False, _tail(result.stderr or result.stdout), []
        trade_date = extract_trade_date(result.stdout)
        if trade_date == expected or config.allow_stale:
            ranking = paths.day_dir / "ranking_deep.csv"
            if not ranking.is_file():
                return False, f"ranking file missing: {ranking}", []
            return True, trade_date or "", parse_ranking(ranking, limit=config.top_n)
        if attempt < config.screen_attempts:
            sleep(float(config.retry_seconds))
    return False, f"screen did not reach trade date {expected}", []


def _ranking_source(path: Path) -> str:
    if not path.is_file():
        return ""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = str(row.get("source") or "").strip()
            if source:
                return source
    return ""


def run_daily(
    paths: DailyPaths,
    config: DailyConfig | None = None,
    *,
    codes: Sequence[str] | None = None,
    skip_screen: bool = False,
    publish: bool = True,
    run_command: CommandRunner = _run_process,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute one daily run and return the status payload."""

    config = config or DailyConfig()
    paths.day_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")
    attempt_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    status: dict[str, Any] = {
        "date": paths.day.isoformat(),
        "attempt_id": attempt_id,
        "started_at": started_at,
        "finished_at": "",
        "trade_date": "",
        "as_of": paths.day.isoformat(),
        "screen_source": "",
        "screen": "skipped" if skip_screen else "pending",
        "stocks": [],
        "site": None,
        "llm_usage": {},
        "ok": False,
    }
    if config.resume and paths.status_path.is_file():
        try:
            prior = json.loads(paths.status_path.read_text(encoding="utf-8"))
            prior_stocks = prior.get("stocks")
            if isinstance(prior_stocks, list):
                status["stocks"] = [row for row in prior_stocks if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            status["stocks"] = []

    with daily_lock(paths.lock_path):
        # The Windows task runs every calendar day.  Do not let a weekend run
        # sit in the trade-date retry loop for 90 minutes; a manual run can
        # still opt in with --allow-stale.
        if (
            paths.day.weekday() >= 5
            and not config.allow_stale
            and not codes
            and not skip_screen
        ):
            status.update(
                {
                    "screen": "skipped",
                    "site": None,
                    "ok": True,
                    "skipped": "weekend",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            _write_json(paths.status_path, status)
            _archive_attempt(paths, status)
            return status
        markets = {str(item).upper() for item in config.markets}
        if not markets or not markets <= {"A", "HK"}:
            raise DailyError(f"unsupported markets: {config.markets!r}")

        if skip_screen:
            selected_codes = list(
                dict.fromkeys(
                    _validate_code(str(code))
                    for code in (codes or [])
                    if str(code).strip()
                )
            )
            if not selected_codes:
                raise DailyError("--skip-screen requires at least one --code")
            selected_a = [code for code in selected_codes if not code.endswith(".HK")]
            selected_hk = [code for code in selected_codes if code.endswith(".HK")]
            selected_codes = selected_a[: config.top_n] + selected_hk[: config.hk_limit]
            if not selected_codes:
                raise DailyError("--skip-screen selected no codes for configured markets")
            ranking = []
            research_counts = {"A": 0, "HK": 0}
            names = _ranking_names(paths.day_dir / "ranking_deep.csv")
            names.update(_ranking_names(paths.day_dir / "ranking_hk.csv"))
            for index, code in enumerate(selected_codes):
                market = "HK" if code.endswith(".HK") else "A"
                research_counts[market] += 1
                ranking.append(
                    {
                        "code": code,
                        "name": names.get(code, HK_DEFAULT_NAMES.get(code, "")),
                        "rank": str(index + 1),
                        "research_rank": str(research_counts[market]),
                        "market": market,
                    }
                )
            status["trade_date"] = expected_trade_date(paths.day)
            status["screen_source"] = (
                _ranking_source(paths.day_dir / "ranking_deep.csv")
                or _ranking_source(paths.day_dir / "ranking_hk.csv")
                or "manual:codes"
            )
        else:
            ranking = []
            if "A" in markets:
                status["screen"] = "running"
                _write_json(paths.status_path, status)
                screen_ok, detail, screened = _screen(
                    paths, config, run_command=run_command, sleep=sleep
                )
                status["screen"] = "ok" if screen_ok else "failed"
                status["trade_date"] = detail if screen_ok else ""
                if not screen_ok:
                    status["error"] = detail
                    status["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    _write_json(paths.status_path, status)
                    _archive_attempt(paths, status)
                    _notify(config, status)
                    return status
                for entry in screened:
                    entry = dict(entry)
                    entry["market"] = "A"
                    entry["research_rank"] = entry.get("rank", "")
                    ranking.append(entry)
                status["screen_source"] = _ranking_source(
                    paths.day_dir / "ranking_deep.csv"
                ) or "tushare:screen"
            else:
                status["screen"] = "skipped"
                status["trade_date"] = expected_trade_date(paths.day)

            if "HK" in markets:
                if config.hk_codes:
                    hk_entries = _hk_ranking(config)
                else:
                    status["hk_screen"] = "running"
                    _write_json(paths.status_path, status)
                    hk_ok, hk_detail, hk_entries = _screen_hk(
                        paths,
                        config,
                        status.get("trade_date") or expected_trade_date(paths.day),
                        run_command=run_command,
                    )
                    status["hk_screen"] = "ok" if hk_ok else "failed"
                    if not hk_ok:
                        status["error"] = hk_detail
                        status["finished_at"] = datetime.now().isoformat(
                            timespec="seconds"
                        )
                        _write_json(paths.status_path, status)
                        _archive_attempt(paths, status)
                        _notify(config, status)
                        return status
                start = len(ranking) + 1
                for index, entry in enumerate(hk_entries[: config.hk_limit]):
                    entry = dict(entry)
                    entry["rank"] = str(start + index)
                    entry["research_rank"] = str(index + 1)
                    ranking.append(entry)
                hk_source = _ranking_source(paths.day_dir / "ranking_hk.csv")
                if hk_source:
                    status["screen_source"] = (
                        f"{status['screen_source']}; {hk_source}"
                        if status["screen_source"]
                        else hk_source
                    )

        completed: set[str] = set()
        for row in status["stocks"]:
            if row.get("status") != "ok":
                continue
            code = str(row.get("code"))
            code_dir = paths.day_dir / code
            if (code_dir / "analysis_report.md").is_file() or (
                code_dir / "analysis_report.html"
            ).is_file():
                completed.add(code)
        status["stocks"] = [
            row for row in status["stocks"] if str(row.get("code")) in completed
        ]
        pending = [entry for entry in ranking if str(entry["code"]) not in completed]
        status["resumed"] = len(ranking) - len(pending)

        def run_one(entry: dict[str, str]) -> dict[str, Any]:
            try:
                record = run_stock(
                    entry["code"],
                    int(entry["rank"]),
                    paths,
                    config,
                    run_command=run_command,
                    market=str(entry.get("market", "A")),
                    research_rank=int(entry.get("research_rank", entry["rank"])),
                )
            except Exception as exc:  # noqa: BLE001
                record = {
                    "code": entry["code"],
                    "rank": entry["rank"],
                    "market": entry.get("market", "A"),
                    "status": "failed",
                    "qa": "UNKNOWN",
                    "error": _tail(f"{type(exc).__name__}: {exc}"),
                    "research": "off",
                }
            record["name"] = entry.get("name", "")
            return record

        if config.report_workers > 1 and len(pending) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=config.report_workers) as pool:
                futures = {pool.submit(run_one, entry): entry for entry in pending}
                for future in as_completed(futures):
                    status["stocks"].append(future.result())
                    status["stocks"].sort(key=lambda row: int(row.get("rank", 0)))
                    _write_json(paths.status_path, status)
        else:
            for entry in pending:
                status["stocks"].append(run_one(entry))
                status["stocks"].sort(key=lambda row: int(row.get("rank", 0)))
                _write_json(paths.status_path, status)
        status["stocks"].sort(key=lambda row: int(row.get("rank", 0)))

        reports = [row for row in status["stocks"] if row["status"] == "ok"]
        failed_stocks = [row for row in status["stocks"] if row["status"] != "ok"]
        should_publish = publish and bool(reports) and (
            config.publish_partial or not failed_stocks
        )
        if should_publish:
            from .site import build_site, publish_site

            try:
                release = build_site(paths.day_dir, paths.site_root)
                publish_site(release, paths.site_root)
                if failed_stocks:
                    status["site"] = (
                        f"partial: {len(failed_stocks)} failed; {release}"
                    )
                else:
                    status["site"] = str(release)
            except (OSError, ValueError) as exc:
                status["site"] = f"error: {exc}"
        elif publish and failed_stocks:
            status["site"] = "skipped: failed stocks; previous release preserved"
        elif publish:
            status["site"] = "skipped: no successful stock"

    failed = [row for row in status["stocks"] if row["status"] != "ok"]
    usage_rows = [
        row.get("research_usage")
        for row in status["stocks"]
        if isinstance(row.get("research_usage"), dict)
    ]
    status["llm_usage"] = {
        "reports_with_usage": len(usage_rows),
        "input_tokens": sum(
            int(row.get("estimated_input_tokens") or 0)
            for row in usage_rows
            if isinstance(row, dict)
        ),
        "max_input_tokens": sum(
            int(row.get("max_input_tokens") or 0)
            for row in usage_rows
            if isinstance(row, dict)
        ),
    }
    status["ok"] = bool(status["stocks"]) and not failed
    status["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(paths.status_path, status)
    _archive_attempt(paths, status)
    _notify(config, status)
    return status


def load_config(path: Path) -> DailyConfig:
    if not path.is_file():
        raise DailyError(f"config file not found: {path}")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DailyError(f"invalid config file: {path}: {exc}") from exc
    known = {field.name for field in DailyConfig.__dataclass_fields__.values()}
    unknown = sorted(set(payload) - known)
    if unknown:
        raise DailyError(f"unknown config keys: {', '.join(unknown)}")
    for key in ("markets", "hk_codes"):
        value = payload.get(key)
        if isinstance(value, list):
            payload[key] = tuple(str(item) for item in value)
    return DailyConfig(**payload)


def result_dict(result: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy (currently a shallow conversion)."""

    value = json.loads(json.dumps(result, default=str))
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def write_result(result: dict[str, Any], path: Path) -> None:
    _write_json(path, result_dict(result))
