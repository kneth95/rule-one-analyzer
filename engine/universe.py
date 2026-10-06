"""The S&P 500 list: parsed from Wikipedia, with last week's saved list as a fallback."""
from html.parser import HTMLParser

import os

import requests

from engine.config import _SYMBOL_RE, normalize_symbol
from engine.output import read_json

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class UniverseError(Exception):
    pass


class _ConstituentsParser(HTMLParser):
    """Collects the cell texts (<th> and <td>) of each row in <table id="constituents">."""

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
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "table":
            self.depth -= 1
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


_COLUMNS = {"symbol": "Symbol", "name": "Security", "sector": "GICS Sector"}


def parse_constituents(html, min_rows=400):
    parser = _ConstituentsParser()
    parser.feed(html)
    if not parser.rows:
        raise UniverseError(f"S&P 500 table had only 0 rows (expected at least {min_rows}); "
                            "the Wikipedia page layout may have changed")
    header = parser.rows[0]
    try:
        index = {key: header.index(title) for key, title in _COLUMNS.items()}
    except ValueError:
        raise UniverseError(f"S&P 500 table is missing the expected columns {list(_COLUMNS.values())}; "
                            f"found {header}") from None
    rows = []
    for r in parser.rows[1:]:
        if len(r) != len(header):
            continue
        symbol = normalize_symbol(r[index["symbol"]])
        if _SYMBOL_RE.match(symbol):
            rows.append({"symbol": symbol, "name": r[index["name"]], "sector": r[index["sector"]]})
    if len(rows) < min_rows:
        raise UniverseError(f"S&P 500 table had only {len(rows)} rows (expected at least {min_rows}); "
                            "the Wikipedia page layout may have changed")
    return rows


def fetch_wikipedia():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    contact = f"https://github.com/{repo}" if repo else "personal research script"
    r = requests.get(WIKI_URL, headers={"User-Agent": f"rule-one-analyzer/1.0 ({contact})"}, timeout=30)
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
