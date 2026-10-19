"""Configuration loading: TOML thresholds + .env secrets."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .types import ConfigError, Market, StockCode, TurtleError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "screening.toml"
DEFAULT_ENV = PROJECT_ROOT / ".env"


def _dec(value: Any, default: str) -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def _str_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(str(v) for v in value)


@dataclass(frozen=True, slots=True)
class ReturnsConfig:
    a_share_floor: Decimal = Decimal("3.5")
    a_share_spread: Decimal = Decimal("2.0")
    hk_floor: Decimal = Decimal("5.0")
    hk_spread: Decimal = Decimal("3.0")
    # Used when the risk-free endpoint is unavailable (e.g. yc_cb permission).
    default_rf: Decimal = Decimal("1.8")
    # Maintenance-capex coefficient bands used by the deterministic G grid.
    g_light: Decimal = Decimal("0.85")
    g_mid: Decimal = Decimal("1.15")
    g_heavy: Decimal = Decimal("1.50")
    g_default: Decimal = Decimal("1.00")

    def threshold(self, rf_pct: Decimal, code: StockCode) -> Decimal:
        """II = max(floor, Rf + spread)."""
        if code.market is Market.HK:
            return max(self.hk_floor, rf_pct + self.hk_spread)
        if code.market is Market.US:
            return max(self.hk_floor, rf_pct + self.hk_spread)
        return max(self.a_share_floor, rf_pct + self.a_share_spread)


@dataclass(frozen=True, slots=True)
class ValuationConfig:
    dividend_discount_floor: Decimal = Decimal("3.0")
    composite_method: str = "median"
    divergence_threshold: Decimal = Decimal("20")

    def validate(self) -> None:
        if self.composite_method not in {"mean", "median"}:
            raise ConfigError(
                f"composite_method must be mean or median, got {self.composite_method!r}"
            )


@dataclass(frozen=True, slots=True)
class ScreeningConfig:
    min_listing_years: int = 3
    min_market_cap_yi: Decimal = Decimal("5")
    min_turnover_pct: Decimal = Decimal("0.1")
    max_pb: Decimal = Decimal("10")
    max_pe: Decimal = Decimal("50")
    excluded_industries: tuple[str, ...] = ("银行", "证券", "保险", "信托", "多元金融")

    min_roe: Decimal = Decimal("8")
    min_gross_margin: Decimal = Decimal("15")
    max_debt_ratio: Decimal = Decimal("70")
    max_pledge_pct: Decimal = Decimal("70")

    obs_channel_limit: int = 50
    tier2_main_limit: int = 150

    min_coverage: float = 0.75
    score_weights: Mapping[str, Decimal] = field(
        default_factory=lambda: {
            "roe_waa": Decimal("0.20"),
            "fcf_yield": Decimal("0.20"),
            "penetration_r": Decimal("0.25"),
            "ev_ebitda": Decimal("0.15"),
            "floor_premium": Decimal("0.20"),
        }
    )

    def validate(self) -> None:
        total = sum(self.score_weights.values())
        if abs(total - Decimal("1")) > Decimal("0.01"):
            raise ConfigError(f"score weights must sum to 1.0, got {total}")
        if not 0 < self.min_coverage <= 1:
            raise ConfigError("min_coverage must be in (0, 1]")
        if self.tier2_main_limit < 1:
            raise ConfigError("tier2_main_limit must be >= 1")


@dataclass(frozen=True, slots=True)
class FxConfig:
    """1 HKD = ``cny_per_hkd`` CNY. Used to put HK quotes into report currency."""

    cny_per_hkd: Decimal = Decimal("0.92")


@dataclass(frozen=True, slots=True)
class Settings:
    screening: ScreeningConfig
    returns: ReturnsConfig
    valuation: ValuationConfig
    fx: FxConfig
    config_path: Path

    def save_snapshot(self) -> dict[str, Any]:
        """Deterministic representation used for report metadata."""
        return {
            "config_path": str(self.config_path),
            "screening": {
                "min_roe": str(self.screening.min_roe),
                "min_gross_margin": str(self.screening.min_gross_margin),
                "max_debt_ratio": str(self.screening.max_debt_ratio),
                "min_coverage": self.screening.min_coverage,
                "weights": {k: str(v) for k, v in sorted(self.screening.score_weights.items())},
            },
            "returns": {
                "a_share_floor": str(self.returns.a_share_floor),
                "a_share_spread": str(self.returns.a_share_spread),
                "hk_floor": str(self.returns.hk_floor),
                "hk_spread": str(self.returns.hk_spread),
                "g_light": str(self.returns.g_light),
                "g_mid": str(self.returns.g_mid),
                "g_heavy": str(self.returns.g_heavy),
            },
            "valuation": {
                "dividend_discount_floor": str(self.valuation.dividend_discount_floor),
                "composite_method": self.valuation.composite_method,
            },
            "fx": {"cny_per_hkd": str(self.fx.cny_per_hkd)},
        }


def load_settings(path: Path | None = None) -> Settings:
    config_path = Path(path) if path else DEFAULT_CONFIG
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
            raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    filters = data.get("filters", {})
    tier2 = data.get("tier2", {})
    channels = data.get("channels", {})
    ranking = data.get("ranking", {})
    weights = ranking.get("weights") or {}

    screening = ScreeningConfig(
        min_listing_years=int(filters.get("min_listing_years", 3)),
        min_market_cap_yi=_dec(filters.get("min_market_cap_yi"), "5"),
        min_turnover_pct=_dec(filters.get("min_turnover_pct"), "0.1"),
        max_pb=_dec(filters.get("max_pb"), "10"),
        max_pe=_dec(filters.get("max_pe"), "50"),
        excluded_industries=_str_tuple(
            filters.get("excluded_industries"),
            ("银行", "证券", "保险", "信托", "多元金融"),
        ),
        min_roe=_dec(tier2.get("min_roe"), "8"),
        min_gross_margin=_dec(tier2.get("min_gross_margin"), "15"),
        max_debt_ratio=_dec(tier2.get("max_debt_ratio"), "70"),
        max_pledge_pct=_dec(tier2.get("max_pledge_pct"), "70"),
        obs_channel_limit=int(channels.get("obs_channel_limit", 50)),
        tier2_main_limit=int(channels.get("tier2_main_limit", 150)),
        min_coverage=float(ranking.get("min_coverage", 0.75)),
        score_weights={
            "roe_waa": _dec(weights.get("roe_waa"), "0.20"),
            "fcf_yield": _dec(weights.get("fcf_yield"), "0.20"),
            "penetration_r": _dec(weights.get("penetration_r"), "0.25"),
            "ev_ebitda": _dec(weights.get("ev_ebitda"), "0.15"),
            "floor_premium": _dec(weights.get("floor_premium"), "0.20"),
        },
    )
    screening.validate()

    returns_data = data.get("returns", {})
    returns = ReturnsConfig(
        a_share_floor=_dec(returns_data.get("a_share_floor"), "3.5"),
        a_share_spread=_dec(returns_data.get("a_share_spread"), "2.0"),
        hk_floor=_dec(returns_data.get("hk_floor"), "5.0"),
        hk_spread=_dec(returns_data.get("hk_spread"), "3.0"),
        default_rf=_dec(returns_data.get("default_rf"), "1.8"),
        g_light=_dec(returns_data.get("g_light"), "0.85"),
        g_mid=_dec(returns_data.get("g_mid"), "1.15"),
        g_heavy=_dec(returns_data.get("g_heavy"), "1.50"),
        g_default=_dec(returns_data.get("g_default"), "1.00"),
    )

    valuation_data = data.get("valuation", {})
    valuation = ValuationConfig(
        dividend_discount_floor=_dec(valuation_data.get("dividend_discount_floor"), "3.0"),
        composite_method=str(valuation_data.get("composite_method", "median")),
        divergence_threshold=_dec(valuation_data.get("divergence_threshold"), "20"),
    )
    valuation.validate()

    fx_data = data.get("fx", {})
    fx = FxConfig(cny_per_hkd=_dec(fx_data.get("cny_per_hkd"), "0.92"))

    return Settings(
        screening=screening,
        returns=returns,
        valuation=valuation,
        fx=fx,
        config_path=config_path,
    )


def load_dotenv(path: Path | None = None) -> None:
    """Load a .env file without overriding existing environment variables."""
    env_path = Path(path) if path else DEFAULT_ENV
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def get_token() -> str:
    load_dotenv()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "TUSHARE_TOKEN is not set. Put it in .env (see .env.sample) "
            "or export it in the environment."
        )
    return token


def get_api_url() -> str | None:
    load_dotenv()
    value = os.environ.get("TUSHARE_API_URL", "").strip()
    return value or None


__all__ = [
    "PROJECT_ROOT",
    "ReturnsConfig",
    "ScreeningConfig",
    "Settings",
    "ValuationConfig",
    "get_api_url",
    "get_token",
    "load_dotenv",
    "load_settings",
    "TurtleError",
]
