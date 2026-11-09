"""Read the dashboard notification list (bell icon). Read-only: never calls ``getNotifications/read``."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .shared.errors import IcegateError
from .shared.session import IcegateSession


class NotificationClient:
    def __init__(self, session: IcegateSession) -> None:
        self.session = session

    def list(self, notification_type: str = "E") -> Any:
        """The portal's notification payload for this account; the shape is returned unchanged."""
        session = self.session
        if session.role_id is None:
            raise IcegateError("login did not provide a role for notifications")
        response = session.send(
            "POST", session.url("/registration/getNotifications/all"),
            json_body={"icegateId": session.settings.icegate_id, "notificationType": notification_type,
                       "roleId": session.role_id},
            headers=session.auth_headers(), timeout=60,
        )
        if response.status_code != 200:
            raise IcegateError(f"notifications request failed with HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise IcegateError("notifications returned invalid JSON") from None


_DATE = r"(\d{8}|\d{4}-\d{2}-\d{2})"
_FILING = re.compile(
    r"Your (shipping bill|bill of entry) filing with (job|sb|be) no\.? (\d+) dated " + _DATE
    + r" has been (successfully submitted|rejected)\.?(?: Error code: ([^\n\"]*))?", re.I)
_VALIDATION = re.compile(
    r"(Header|Field|DSC) validation failed for control no\.? (\d+), filing date " + _DATE
    + r", Receiver ID (\w+)", re.I)
_PROCESSING = re.compile(
    r"error in processing your file with control no\.? (\d+), filing date " + _DATE + r", Receiver ID (\w+)", re.I)


def _iso(text: str) -> str | None:
    """Portal dates in these messages are YYYYMMDD, DDMMYYYY or YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d%m%Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if parsed.year >= 2020:
            return parsed.isoformat()
    return None


def _tidy(message: str) -> str:
    """One line without the greeting, sign-off or stray quotes the portal wraps around every message."""
    text = " ".join(message.split()).strip('" ')
    text = re.sub(r"^Dear Sir/Madam,\s*", "", text)
    text = re.sub(r"\s*(Regards,?\s*ICEGATE Support Team|-CBIC)\s*\"?$", "", text)
    return text.strip('" ')


def parse_notification(message: str) -> dict[str, Any] | None:
    """A filing outcome from one portal message, or None for anything else.

    ``outcome`` is ``submitted`` (accepted for processing, not final), ``rejected`` or ``failed``.
    ``job`` is the job number, or the control number for validation failures (they are the same file field).
    """
    text = _tidy(message)
    if match := _FILING.search(message):
        kind, label, number, day, verdict, codes = match.groups()
        by_job = label.lower() == "job"
        rejected = verdict.lower() == "rejected"
        return {"outcome": "rejected" if rejected else "submitted", "doc": "SB" if kind.lower().startswith("s") else "BE",
                "job": number if by_job else None, "number": None if by_job else number,
                "date": _iso(day), "location": None,
                "detail": f"error code {codes.strip()}" if rejected and codes and codes.strip() else "", "message": text}
    if match := _VALIDATION.search(message):
        stage, job, day, location = match.groups()
        extra = message.split("Errors:", 1)[1].strip() if "Errors:" in message else ""
        return {"outcome": "failed", "doc": None, "job": job, "number": None, "date": _iso(day), "location": location.upper(),
                "detail": f"{stage.lower()} validation failed" + (f": {' '.join(extra.split())[:300]}" if extra else ""),
                "message": text}
    if match := _PROCESSING.search(message):
        job, day, location = match.groups()
        return {"outcome": "failed", "doc": None, "job": job, "number": None, "date": _iso(day), "location": location.upper(),
                "detail": "portal error while processing the file; check the portal before retrying", "message": text}
    return None


def filing_events(notifications: Any) -> list[dict[str, Any]]:
    """Parsed outcomes, newest first (the portal's order). Unrelated notifications are dropped."""
    if not isinstance(notifications, list):
        raise IcegateError("notifications returned an unexpected response")
    events = []
    for item in notifications:
        if isinstance(item, dict) and isinstance(item.get("message"), str) and (event := parse_notification(item["message"])):
            events.append({**event, "created": item.get("createdDate")})
    return events
