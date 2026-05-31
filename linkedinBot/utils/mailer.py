"""SMTP sender for outreach emails. Uses Gmail's smtp.gmail.com:587 with TLS
and a Google App Password (not your normal password — create one at
https://myaccount.google.com/apppasswords).
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import pandas as pd


@dataclass
class GmailCreds:
    user: str
    app_password: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587


def _render(template: str, fields: dict) -> str:
    try:
        return template.format(**fields)
    except (KeyError, IndexError):
        return template


def send_one(creds: GmailCreds, to_addr: str, subject: str, body: str, from_name: str = "") -> None:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{creds.user}>" if from_name else creds.user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP(creds.smtp_host, creds.smtp_port, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(creds.user, creds.app_password)
        s.send_message(msg)


def send_to_recruiters(
    connections_csv: str,
    subject_template: str,
    body_template: str,
    creds: GmailCreds,
    candidate_ctx: dict,
    dry_run: bool = False,
    only_unsent: bool = True,
) -> dict:
    """Iterate `connections.csv`, render the subject/body for each row with an
    email, and SMTP-send. Marks `email_sent=True` per row.

    Returns a summary dict with counts.
    """
    df = pd.read_csv(connections_csv)
    if "email_sent" not in df.columns:
        df["email_sent"] = False
    df["email_sent"] = df["email_sent"].fillna(False).astype(bool)

    candidates = df[df["email"].astype(str).str.contains("@", na=False)]
    if only_unsent:
        candidates = candidates[~candidates["email_sent"]]

    sent, skipped, failed = 0, 0, 0
    for idx, row in candidates.iterrows():
        to_addr = (row.get("email") or "").strip()
        if not to_addr or "@" not in to_addr:
            skipped += 1
            continue
        fields = {
            "name": (row.get("profile_name") or "there").split()[0],
            "job_title": row.get("job_title") or "this role",
            "company": row.get("company_name") or "your company",
            **candidate_ctx,
        }
        subject = _render(subject_template, fields)
        body = _render(body_template, fields)

        if dry_run:
            sent += 1
            continue
        try:
            send_one(
                creds=creds,
                to_addr=to_addr,
                subject=subject,
                body=body,
                from_name=candidate_ctx.get("candidate_name", ""),
            )
            df.at[idx, "email_sent"] = True
            df.to_csv(connections_csv, index=False)
            sent += 1
        except Exception as e:
            print(f"[mailer] {to_addr} failed: {e}")
            failed += 1

    return {"sent": sent, "skipped": skipped, "failed": failed, "total": len(candidates)}


def gmail_creds_from_env() -> GmailCreds | None:
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return None
    return GmailCreds(user=user, app_password=pw)
