from __future__ import annotations
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("apthunt.email")


def new_match_count(ctx) -> int:
    return sum(1 for c in (*ctx.apply, *ctx.consider) if c.is_new)


def build_email(profile, ctx, report_url: str) -> EmailMessage:
    n = new_match_count(ctx)
    msg = EmailMessage()
    msg["Subject"] = f"{n} new apartment match{'es' if n != 1 else ''} — {profile.name}"
    msg["To"] = profile.email
    lines = [f"<p>{n} new match(es). <a href='{report_url}'>Open full report</a></p><ul>"]
    for c in (*ctx.apply, *ctx.consider):
        if c.is_new:
            lines.append(f"<li><b>{c.grade}</b> — ${c.price}/mo, {c.beds}bd, "
                         f"{c.neighborhood} — <a href='{c.url}'>{c.address}</a><br>{c.summary}</li>")
    lines.append("</ul>")
    msg.set_content("New matches — open in an HTML-capable client.")
    msg.add_alternative("".join(lines), subtype="html")
    return msg


def send_email(msg: EmailMessage, *, smtp=None) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.warning("SMTP not configured; skipping email to %s", msg["To"])
        return
    smtp = smtp or smtplib.SMTP
    msg["From"] = os.environ["MAIL_FROM"]
    with smtp(host, int(os.environ.get("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)
