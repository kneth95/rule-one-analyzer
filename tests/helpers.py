from engine.financials import Financials


def fact(start, end, val, filed, form="10-K"):
    row = {"end": end, "val": val, "filed": filed, "form": form, "fp": "FY"}
    if start:
        row["start"] = start
    return row


def facts_doc(concepts, units=None):
    """concepts: {concept_name: [rows]}; units: optional {concept_name: unit}."""
    units = units or {}
    return {
        "entityName": "Test Co",
        "facts": {"us-gaap": {
            name: {"units": {units.get(name, "USD"): rows}} for name, rows in concepts.items()
        }},
    }


def make_fin(series, name="Test Co"):
    years = sorted({y for s in series.values() for y in s})
    return Financials(
        name=name,
        years=years,
        fy_end={y: f"{y}-12-31" for y in years},
        data={k: dict(v) for k, v in series.items()},
        warnings=[],
    )
