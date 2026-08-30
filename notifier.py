"""Email delivery of finished analyses via the Resend API.

Every completed generation is mailed to the configured recipient with a summary
of the analysis in the body and the rendered one-pager attached. The email body
is built from ``template.py`` — like ``analyzer.py``, this module keeps no field
list of its own, so template changes flow through automatically.

Notification is best-effort: ``notify_analysis`` never raises, so a Resend
outage or a misconfigured sender cannot fail a generation the user is waiting on.
"""

from __future__ import annotations

import base64
import html
import logging
import os
from datetime import datetime, timezone

import httpx

import template

logger = logging.getLogger("onepager.notifier")

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_TO = "Info@tencapital.group"
DEFAULT_FROM = f"{template.ORGANIZATION} Analyzer <onepager@tencapital.group>"
REQUEST_TIMEOUT = 20.0

# Resend caps a request at 40 MB and base64 inflates bytes by 4/3, so stay well under.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


class NotificationError(RuntimeError):
    """Raised when the notification email cannot be sent."""


def is_configured() -> bool:
    """Return whether a Resend API key is available to send with."""
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def recipients() -> list[str]:
    """Return the configured recipient list, split on commas."""
    raw = os.environ.get("NOTIFY_EMAIL_TO", DEFAULT_TO)
    return [address.strip() for address in raw.split(",") if address.strip()]


def notify_analysis(
    analysis: dict[str, str],
    pdf_bytes: bytes | None = None,
    *,
    filename: str = "onepager.pdf",
    source_name: str = "deck",
    origin: str = "web",
) -> bool:
    """Send the results email, swallowing any failure.

    Args:
        analysis: The completed analysis, keyed by ``template.field_keys()``.
        pdf_bytes: Rendered one-pager to attach. Omitted when unavailable.
        filename: Attachment filename.
        source_name: Original deck filename, shown in the subject and body.
        origin: Where the run came from — ``"web"`` or ``"cli"``.

    Returns:
        True if Resend accepted the message, False if it was skipped or failed.
    """
    if not is_configured():
        logger.debug("RESEND_API_KEY not set; skipping results email")
        return False
    try:
        message_id = send_analysis_email(
            analysis,
            pdf_bytes,
            filename=filename,
            source_name=source_name,
            origin=origin,
        )
    except NotificationError as exc:
        logger.warning("results email not sent for %s: %s", source_name, exc)
        return False
    logger.info("results email sent for %s (resend id %s)", source_name, message_id)
    return True


def send_analysis_email(
    analysis: dict[str, str],
    pdf_bytes: bytes | None = None,
    *,
    filename: str = "onepager.pdf",
    source_name: str = "deck",
    origin: str = "web",
) -> str:
    """Send the results email and return the Resend message ID.

    Raises:
        NotificationError: No API key, no recipients, or Resend rejected the
            request or was unreachable.
    """
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        raise NotificationError("RESEND_API_KEY is not set.")

    to_addresses = recipients()
    if not to_addresses:
        raise NotificationError("NOTIFY_EMAIL_TO is empty; nowhere to send.")

    company = analysis.get(template.TITLE_KEY) or "Unknown company"
    payload: dict[str, object] = {
        "from": os.environ.get("NOTIFY_EMAIL_FROM", DEFAULT_FROM),
        "to": to_addresses,
        "subject": f"{template.DOCUMENT_LABEL}: {company}",
        "html": build_html_body(analysis, source_name=source_name, origin=origin),
        "text": build_text_body(analysis, source_name=source_name, origin=origin),
    }

    reply_to = os.environ.get("NOTIFY_EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to

    if pdf_bytes:
        if len(pdf_bytes) > MAX_ATTACHMENT_BYTES:
            logger.warning(
                "one-pager for %s is %d bytes; sending summary without attachment",
                source_name,
                len(pdf_bytes),
            )
        else:
            payload["attachments"] = [
                {
                    "filename": filename,
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                }
            ]

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise NotificationError(f"Could not reach Resend: {exc}") from exc

    if response.status_code >= 400:
        raise NotificationError(_describe_failure(response))

    try:
        return str(response.json().get("id", ""))
    except ValueError:
        return ""


def _describe_failure(response: httpx.Response) -> str:
    """Turn a Resend error response into an actionable message."""
    try:
        detail = response.json().get("message") or response.text
    except ValueError:
        detail = response.text
    detail = detail.strip()[:400]
    if response.status_code in (401, 403):
        detail += (
            " — check RESEND_API_KEY and that the NOTIFY_EMAIL_FROM domain is verified "
            "at https://resend.com/domains."
        )
    return f"Resend returned {response.status_code}: {detail}"


# --- body construction ------------------------------------------------------


def _summary_rows(analysis: dict[str, str]) -> list[tuple[str, str]]:
    """Return (label, value) pairs for the email body, in template order."""
    rows: list[tuple[str, str]] = []
    for callout in template.CALLOUTS:
        headline = analysis.get(callout.headline_key, template.FALLBACK_VALUE)
        body = analysis.get(callout.body_key, "")
        rows.append((callout.label, f"{headline} — {body}" if body else headline))
    for section in template.SECTIONS:
        rows.append((section.label, analysis.get(section.key, template.FALLBACK_VALUE)))
    return rows


def _metadata(source_name: str, origin: str) -> list[tuple[str, str]]:
    """Return provenance rows shown above the analysis."""
    return [
        ("Source deck", source_name),
        ("Generated", datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")),
        ("Model", os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")),
        ("Origin", origin),
    ]


def build_html_body(analysis: dict[str, str], *, source_name: str, origin: str) -> str:
    """Render the HTML email body for a completed analysis."""
    company = html.escape(analysis.get(template.TITLE_KEY) or "Unknown company")
    tagline = html.escape(analysis.get(template.SUBTITLE_KEY) or "")

    meta = "".join(
        '<tr>'
        f'<td style="padding:2px 16px 2px 0;color:#6b7280;white-space:nowrap;">{html.escape(label)}</td>'
        f'<td style="padding:2px 0;color:#111827;">{html.escape(value)}</td>'
        '</tr>'
        for label, value in _metadata(source_name, origin)
    )

    blocks = "".join(
        f'<h2 style="font-size:13px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:#6b7280;margin:22px 0 4px;">{html.escape(label)}</h2>'
        f'<p style="margin:0;font-size:15px;line-height:1.55;color:#111827;">{html.escape(value)}</p>'
        for label, value in _summary_rows(analysis)
    )

    return f"""\
<div style="font-family:'Open Sans',Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;">
  <p style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#6b7280;margin:0 0 4px;">
    {html.escape(template.ORGANIZATION)} &middot; {html.escape(template.DOCUMENT_LABEL)}
  </p>
  <h1 style="font-size:24px;margin:0 0 4px;color:#111827;">{company}</h1>
  <p style="margin:0 0 20px;font-size:15px;color:#374151;">{tagline}</p>
  <table style="font-size:12px;border-collapse:collapse;margin-bottom:8px;">{meta}</table>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
  {blocks}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 12px;">
  <p style="font-size:11px;color:#6b7280;line-height:1.5;margin:0;">{html.escape(template.DISCLOSURE)}</p>
</div>"""


def build_text_body(analysis: dict[str, str], *, source_name: str, origin: str) -> str:
    """Render the plain-text fallback body for a completed analysis."""
    lines = [
        f"{template.ORGANIZATION} — {template.DOCUMENT_LABEL}",
        "",
        analysis.get(template.TITLE_KEY) or "Unknown company",
    ]
    tagline = analysis.get(template.SUBTITLE_KEY)
    if tagline:
        lines.append(tagline)
    lines.append("")
    lines += [f"{label}: {value}" for label, value in _metadata(source_name, origin)]
    for label, value in _summary_rows(analysis):
        lines += ["", label.upper(), value]
    lines += ["", template.DISCLOSURE]
    return "\n".join(lines)
