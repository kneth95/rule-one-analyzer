"""The S&P 500 list: parsed from Wikipedia, with last week's saved list as a fallback."""
from html.parser import HTMLParser

import requests

from engine.config import normalize_symbol
from engine.output import read_json

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class UniverseError(Exception):
    pass


class _ConstituentsParser(HTMLParser):
    """Collects the <td> texts of each row in <table id="constituents">."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # table nesting depth inside the constituents table; 0 = outside
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.depth:
                self.depth += 1
            elif dict(attrs).get("id") == "constituents":
                self.depth = 1
            return
        if self.depth != 1:
            return
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "table":
            self.depth -= 1
        elif tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) >= 3:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_constituents(html, min_rows=400):
    parser = _ConstituentsParser()
    parser.feed(html)
    rows = [{"symbol": normalize_symbol(r[0]), "name": r[1], "sector": r[2]} for r in parser.rows if r[0]]
    if len(rows) < min_rows:
        raise UniverseError(f"S&P 500 table had only {len(rows)} rows (expected at least {min_rows}); "
                            "the Wikipedia page layout may have changed")
    return rows


def fetch_wikipedia():
    r = requests.get(WIKI_URL, headers={"User-Agent": "rule-one-analyzer (GitHub Actions)"}, timeout=30)
    r.raise_for_status()
    return r.text


def load_universe(fetch_html, saved_path, min_rows=400):
    try:
        return parse_constituents(fetch_html(), min_rows), "wikipedia", []
    except Exception as e:
        saved = read_json(saved_path, None)
        if saved:
            return saved, "saved", [f"Couldn't load the S&P 500 list from Wikipedia ({e}); used last week's saved list."]
        raise UniverseError(f"Couldn't load the S&P 500 list ({e}) and there is no saved list.") from e
