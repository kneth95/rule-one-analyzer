"""Assign each stock a status tier with a plain-English reason."""

TIER_RANK = {"not_yet": 0, "close": 1, "buy": 2}
TIER_LABEL = {"buy": "Buy zone", "close": "Getting close", "not_yet": "Not yet"}


def assign_tier(price, mos_price, score, settings):
    min_score = int(settings["big_five_min_score"])
    if price is None or mos_price is None:
        return "not_yet", "Not yet: a MOS price couldn't be calculated (see the warnings)."
    if score < min_score:
        return "not_yet", f"Not yet: only {score} of 5 Big Five numbers pass (needs {min_score})."
    pct = price / mos_price - 1
    if price <= mos_price:
        return "buy", (f"Buy zone: the price (${price:,.2f}) is at or below the MOS price "
                       f"(${mos_price:,.2f}) and {score} of 5 Big Five numbers pass.")
    margin = settings["getting_close_margin"]
    if price <= mos_price * (1 + margin):
        return "close", (f"Getting close: the price is {pct:.1%} above the MOS price, "
                         f"within the {margin:.0%} early-warning range.")
    return "not_yet", f"Not yet: the price is {pct:.0%} above the MOS price."
