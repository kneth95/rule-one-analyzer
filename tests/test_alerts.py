import pytest

from engine.alerts import EmailConfig, compose_email, detect_changes, email_config_from_env, send_email


def stock(symbol, tier, **extra):
    s = {"symbol": symbol, "name": f"{symbol} Inc.", "tier": tier, "tier_reason": f"{tier} reason",
         "price": 90.0, "stale": False, "error": None, "warnings": [],
         "big_five": {"score": 5, "debt": {"payoff_years": 1.5, "pass": True}},
         "valuation": {"mos_price": 100.0, "sticker_price": 200.0, "pct_from_mos": -0.1,
                       "ten_cap_price": 95.0, "payback_price": 120.0}}
    s.update(extra)
    return s


def test_detects_upgrades_only():
    stocks = [stock("AAA", "buy"), stock("BBB", "close"), stock("CCC", "not_yet"), stock("DDD", "close")]
    state = {"AAA": "close", "BBB": "close", "CCC": "buy", "DDD": "buy"}
    alerts, new_state = detect_changes(stocks, state)
    assert [a["symbol"] for a in alerts] == ["AAA"]
    assert new_state == {"AAA": "buy", "BBB": "close", "CCC": "not_yet", "DDD": "close"}


def test_new_symbol_alerts_from_not_yet():
    alerts, _ = detect_changes([stock("NEW", "close")], {})
    assert [a["symbol"] for a in alerts] == ["NEW"]


def test_stale_and_error_never_alert_and_keep_state():
    stocks = [stock("OLD", "buy", stale=True), stock("BAD", "not_yet", error="boom")]
    alerts, new_state = detect_changes(stocks, {"OLD": "close", "BAD": "close"})
    assert alerts == []
    assert new_state == {"OLD": "close", "BAD": "close"}


def test_removed_symbols_dropped_from_state():
    _, new_state = detect_changes([stock("AAA", "not_yet")], {"AAA": "not_yet", "GONE": "buy"})
    assert new_state == {"AAA": "not_yet"}


def test_email_config_from_env():
    env = {"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "pw", "ALERT_EMAIL_TO": "you@x.com"}
    assert email_config_from_env(env) == EmailConfig("me@gmail.com", "pw", "you@x.com")
    assert email_config_from_env({"GMAIL_ADDRESS": "me@gmail.com"}) is None


def test_compose_email():
    subject, text, html = compose_email([stock("AAPL", "buy"), stock("MSFT", "close")], "https://me.github.io/r1/")
    assert subject == "Rule #1: AAPL in Buy zone, MSFT getting close"
    assert "https://me.github.io/r1/stock.html?t=AAPL" in text
    assert "$100.00" in text
    assert "<a href=\"https://me.github.io/r1/stock.html?t=MSFT\">" in html


def test_compose_email_escapes_html():
    s = stock("XYZ", "buy", name="<b>Evil</b> & Co")
    _, _, html = compose_email([s], "https://x/")
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in html


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sent, self.login_args = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def test_send_email_uses_gmail_ssl():
    cfg = EmailConfig("me@gmail.com", "pw", "you@x.com")
    send_email("Subj", "plain", "<p>html</p>", cfg, smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 465)
    assert smtp.login_args == ("me@gmail.com", "pw")
    msg = smtp.sent[0]
    assert msg["To"] == "you@x.com" and msg["Subject"] == "Subj"
