"""Tier-change detection and Gmail alert emails."""
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from engine.tiers import TIER_LABEL, TIER_RANK


@dataclass
class EmailConfig:
    address: str
    password: str
    to: str


def email_config_from_env(env):
    address, password, to = env.get("GMAIL_ADDRESS"), env.get("GMAIL_APP_PASSWORD"), env.get("ALERT_EMAIL_TO")
    if not (address and password and to):
        return None
    return EmailConfig(address, password, to)


def detect_changes(stocks, state):
    alerts, new_state = [], dict(state)
    for s in stocks:
        if s.get("stale") or s.get("error"):
            continue
        previous = state.get(s["symbol"], "not_yet")
        if TIER_RANK[s["tier"]] > TIER_RANK[previous]:
            alerts.append(s)
        new_state[s["symbol"]] = s["tier"]
    symbols = {s["symbol"] for s in stocks}
    return alerts, {k: v for k, v in new_state.items() if k in symbols}


def _money(v):
    return "n/a" if v is None else f"${v:,.2f}"


def _pct(v):
    return "n/a" if v is None else f"{v:+.1%}"


def _lines(s):
    val, bf = s["valuation"], s["big_five"]
    debt = bf["debt"]
    debt_text = "n/a" if debt["payoff_years"] is None else f"{debt['payoff_years']:.1f} years"
    return [
        ("Price", _money(s["price"])),
        ("MOS price", _money(val["mos_price"])),
        ("Price vs MOS", _pct(val["pct_from_mos"])),
        ("Sticker Price", _money(val["sticker_price"])),
        ("Big Five score", f"{bf['score']} of 5"),
        ("Debt payoff", f"{debt_text} ({'pass' if debt['pass'] else 'fail'})"),
        ("Ten Cap price", _money(val["ten_cap_price"])),
        ("Payback Time price", _money(val["payback_price"])),
    ]


def compose_email(alerts, site_url):
    parts = [f"{s['symbol']} in Buy zone" if s["tier"] == "buy" else f"{s['symbol']} getting close" for s in alerts]
    subject = "Rule #1: " + ", ".join(parts)
    text, html = [], ["<div style=\"font-family:system-ui,sans-serif;max-width:600px\">"]
    for s in alerts:
        link = f"{site_url}stock.html?t={s['symbol']}"
        label = TIER_LABEL[s["tier"]]
        text.append(f"{s['symbol']} — {s['name']}: {label}")
        text.append(s["tier_reason"])
        text += [f"  {k}: {v}" for k, v in _lines(s)]
        text += [f"  Warning: {w}" for w in s.get("warnings", [])]
        text += [f"  Details: {link}", ""]
        rows = "".join(f"<tr><td style=\"padding:2px 12px 2px 0;color:#555\">{escape(k)}</td>"
                       f"<td><b>{escape(v)}</b></td></tr>" for k, v in _lines(s))
        warns = "".join(f"<li>{escape(w)}</li>" for w in s.get("warnings", []))
        html.append(
            f"<h2 style=\"margin-bottom:4px\">{escape(s['symbol'])} — {escape(s['name'])}</h2>"
            f"<p style=\"margin-top:0\"><b>{escape(label)}</b>: {escape(s['tier_reason'])}</p>"
            f"<table>{rows}</table>"
            + (f"<p>Warnings:</p><ul>{warns}</ul>" if warns else "")
            + f"<p><a href=\"{escape(link)}\">Open {escape(s['symbol'])} on the dashboard</a></p><hr>"
        )
    footer = "You get this email when a stock on your watchlist moves into a better tier."
    text.append(footer)
    html.append(f"<p style=\"color:#777;font-size:12px\">{footer}</p></div>")
    return subject, "\n".join(text), "".join(html)


def send_email(subject, text, html, cfg, smtp_factory=smtplib.SMTP_SSL):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg.address, cfg.to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtp_factory("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(cfg.address, cfg.password)
        smtp.send_message(msg)
