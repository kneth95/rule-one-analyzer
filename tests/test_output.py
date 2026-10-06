import csv
import io

from engine.output import HISTORY_COLUMNS, read_json, stock_csv, watchlist_csv, write_csvs, write_json


def sample_stock():
    return {
        "symbol": "AAA", "name": "Aaa, Inc.", "price": 50.0, "tier": "close", "stale": False, "error": None,
        "big_five": {"score": 4, "debt": {"payoff_years": 2.0, "pass": True}},
        "valuation": {"mos_price": 48.0, "sticker_price": 96.0, "pct_from_mos": 0.0417,
                      "ten_cap_price": 40.0, "payback_price": 55.0, "growth_rate": 0.12},
        "history": {"years": [2023, 2024], "fy_end": {"2023": "2023-12-31", "2024": "2024-12-31"},
                    "revenue": {"2023": 100.0, "2024": 112.0}, "roic": {"2024": 0.2}},
    }


def test_json_roundtrip(tmp_path):
    p = tmp_path / "sub" / "x.json"
    write_json(p, {"a": 1})
    assert read_json(p, None) == {"a": 1}
    assert read_json(tmp_path / "missing.json", {"d": 0}) == {"d": 0}


def test_stock_csv_rows_per_year():
    rows = list(csv.reader(io.StringIO(stock_csv(sample_stock()))))
    labels = dict(HISTORY_COLUMNS)
    assert rows[0][:3] == ["Year", "Fiscal year end", labels["revenue"]]
    assert rows[1][:3] == ["2023", "2023-12-31", "100.0"]
    roic_col = rows[0].index(labels["roic"])
    assert rows[1][roic_col] == "" and rows[2][roic_col] == "0.2"


def test_watchlist_csv():
    rows = list(csv.reader(io.StringIO(watchlist_csv([sample_stock()]))))
    assert rows[0][:4] == ["Symbol", "Company", "Status", "Price"]
    assert rows[1][:4] == ["AAA", "Aaa, Inc.", "Getting close", "50.0"]


def test_write_csvs(tmp_path):
    write_csvs([sample_stock(), {"symbol": "BAD", "name": "", "error": "x", "tier": "not_yet"}], tmp_path)
    assert (tmp_path / "watchlist.csv").exists()
    assert (tmp_path / "AAA.csv").exists()
    assert not (tmp_path / "BAD.csv").exists()
