"""Loading and validating settings.json and watchlist.json."""
import json
import re
from pathlib import Path

DEFAULT_SETTINGS = {
    "marr": 0.15,
    "mos_fraction": 0.5,
    "growth_cap": 0.15,
    "pe_cap": 50,
    "big_five_threshold": 0.10,
    "big_five_min_score": 4,
    "windows_to_pass": 3,
    "trend_tolerance": 0.10,
    "debt_payoff_max_years": 3,
    "getting_close_margin": 0.10,
    "payback_years": 8,
}

_RANGES = {
    "marr": (0.01, 1.0),
    "mos_fraction": (0.05, 1.0),
    "growth_cap": (0.01, 1.0),
    "pe_cap": (1, 500),
    "big_five_threshold": (0.0, 1.0),
    "big_five_min_score": (0, 5),
    "windows_to_pass": (1, 4),
    "trend_tolerance": (0.0, 1.0),
    "debt_payoff_max_years": (0, 100),
    "getting_close_margin": (0.0, 1.0),
    "payback_years": (1, 30),
}
_INT_KEYS = {"big_five_min_score", "windows_to_pass", "payback_years"}
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


class ConfigError(ValueError):
    pass


def _read(path: Path, label: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"{label} could not be read: {e}") from e


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_settings(path) -> dict:
    raw = _read(path, "settings.json")
    if not isinstance(raw, dict):
        raise ConfigError("settings.json must be a JSON object")
    unknown = set(raw) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ConfigError(f"settings.json has unknown keys: {', '.join(sorted(unknown))}")
    settings = {**DEFAULT_SETTINGS, **raw}
    for key, (lo, hi) in _RANGES.items():
        v = settings[key]
        if not _is_number(v):
            raise ConfigError(f"settings.{key} must be a number")
        if key in _INT_KEYS and int(v) != v:
            raise ConfigError(f"settings.{key} must be a whole number")
        if not lo <= v <= hi:
            raise ConfigError(f"settings.{key} must be between {lo} and {hi}, got {v}")
    return settings


def normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace(".", "-")


def load_watchlist(path) -> list[dict]:
    raw = _read(path, "watchlist.json")
    if not isinstance(raw, dict) or not isinstance(raw.get("tickers"), list):
        raise ConfigError('watchlist.json must look like {"tickers": [...]}')
    seen, out = set(), []
    for item in raw["tickers"]:
        if not isinstance(item, dict) or "symbol" not in item:
            raise ConfigError("each watchlist entry needs a symbol")
        symbol = normalize_symbol(item["symbol"])
        if not _SYMBOL_RE.match(symbol):
            raise ConfigError(f"watchlist symbol {item['symbol']!r} is not a valid ticker")
        override = item.get("growth_override")
        if override is not None and (not _is_number(override) or not 0 < override <= 1):
            raise ConfigError(f"{symbol}: growth_override must be a decimal between 0 and 1 (e.g. 0.12)")
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol,
            "added": item.get("added", ""),
            "notes": item.get("notes", ""),
            "growth_override": override,
        })
    return out
