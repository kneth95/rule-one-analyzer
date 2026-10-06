from pathlib import Path

import pytest

from engine.output import write_json
from engine.universe import UniverseError, load_universe, parse_constituents

SAMPLE = (Path(__file__).parent / "fixtures" / "sp500_sample.html").read_text(encoding="utf-8")


def test_parses_constituents_table_only():
    rows = parse_constituents(SAMPLE, min_rows=1)
    assert rows == [
        {"symbol": "MMM", "name": "3M", "sector": "Industrials"},
        {"symbol": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financials"},
        {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology"},
    ]


def test_rejects_short_table():
    with pytest.raises(UniverseError, match="only 3 rows"):
        parse_constituents(SAMPLE)


def test_rejects_missing_table():
    with pytest.raises(UniverseError, match="only 0 rows"):
        parse_constituents("<html><table><tr><td>a</td><td>b</td><td>c</td></tr></table></html>", min_rows=1)


def test_load_from_wikipedia(tmp_path):
    rows, source, warnings = load_universe(lambda: SAMPLE, tmp_path / "sp500.json", min_rows=1)
    assert source == "wikipedia" and len(rows) == 3 and warnings == []


def test_falls_back_to_saved_list(tmp_path):
    saved = tmp_path / "sp500.json"
    write_json(saved, [{"symbol": "KO", "name": "Coca-Cola", "sector": "Consumer Staples"}])

    def down():
        raise OSError("no network")

    rows, source, warnings = load_universe(down, saved, min_rows=1)
    assert source == "saved" and rows[0]["symbol"] == "KO"
    assert "last week's saved list" in warnings[0] and "no network" in warnings[0]


def test_fails_without_saved_list(tmp_path):
    with pytest.raises(UniverseError, match="no saved list"):
        load_universe(lambda: "<html></html>", tmp_path / "missing.json")
