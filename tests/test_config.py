import json

import pytest

from engine.config import DEFAULT_SETTINGS, ConfigError, load_settings, load_watchlist


def write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def test_settings_defaults_fill_missing_keys(tmp_path):
    s = load_settings(write(tmp_path, "s.json", {"marr": 0.12}))
    assert s["marr"] == 0.12
    assert s["mos_fraction"] == DEFAULT_SETTINGS["mos_fraction"]


def test_settings_rejects_unknown_key(tmp_path):
    with pytest.raises(ConfigError, match="unknown keys: bogus"):
        load_settings(write(tmp_path, "s.json", {"bogus": 1}))


def test_settings_rejects_out_of_range(tmp_path):
    with pytest.raises(ConfigError, match="marr"):
        load_settings(write(tmp_path, "s.json", {"marr": 5}))


def test_settings_rejects_non_integer_score(tmp_path):
    with pytest.raises(ConfigError, match="whole number"):
        load_settings(write(tmp_path, "s.json", {"big_five_min_score": 3.5}))


def test_settings_rejects_bad_json(tmp_path):
    with pytest.raises(ConfigError, match="could not be read"):
        load_settings(write(tmp_path, "s.json", "{not json"))


def test_watchlist_normalizes_and_dedupes(tmp_path):
    p = write(tmp_path, "w.json", {"tickers": [
        {"symbol": " aapl "}, {"symbol": "BRK.B", "notes": "insurance"}, {"symbol": "AAPL"}]})
    w = load_watchlist(p)
    assert [t["symbol"] for t in w] == ["AAPL", "BRK-B"]
    assert w[1]["notes"] == "insurance"
    assert w[0]["growth_override"] is None


def test_watchlist_rejects_bad_symbol(tmp_path):
    with pytest.raises(ConfigError, match="symbol"):
        load_watchlist(write(tmp_path, "w.json", {"tickers": [{"symbol": "not a ticker!"}]}))


def test_watchlist_rejects_bad_override(tmp_path):
    with pytest.raises(ConfigError, match="growth_override"):
        load_watchlist(write(tmp_path, "w.json", {"tickers": [{"symbol": "KO", "growth_override": 3}]}))
