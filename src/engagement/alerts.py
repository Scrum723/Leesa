"""Deliver alerts via macOS notification + optional webhook."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

import httpx

from .. import db
from ..config import Settings
from ..logging_setup import EventLog

log = logging.getLogger("liaison.alerts")


class AlertService:
    def __init__(self, settings: Settings, events: EventLog | None = None) -> None:
        self.settings = settings
        self.events = events or EventLog()
        self._last_pushed_id = 0

    def push_unacknowledged(self) -> int:
        alerts = db.list_alerts(limit=20, unacked_only=True)
        n = 0
        for a in alerts:
            if int(a["id"]) <= self._last_pushed_id and self._last_pushed_id:
                # still notify new ones only by tracking max id seen this session
                pass
            self._deliver(a)
            self._last_pushed_id = max(self._last_pushed_id, int(a["id"]))
            n += 1
        return n

    def notify_now(
        self,
        title: str,
        body: str = "",
        severity: str = "info",
        category: str = "manual",
        platform: str = "",
    ) -> int:
        aid = db.create_alert(severity, category, title, body, platform)
        self._deliver(
            {
                "id": aid,
                "severity": severity,
                "category": category,
                "title": title,
                "body": body,
                "platform": platform,
            }
        )
        return aid

    def _deliver(self, alert: dict[str, Any]) -> None:
        title = f"[{alert.get('severity', 'info').upper()}] {alert.get('title', 'Alert')}"
        body = alert.get("body") or ""
        self.events.write("alert", **{k: alert.get(k) for k in ("id", "severity", "category", "title", "platform")})
        self._macos(title, body)
        self._webhook(title, body, alert)

    def _macos(self, title: str, body: str) -> None:
        # Escape for AppleScript
        t = title.replace("\\", "\\\\").replace('"', '\\"')
        b = body.replace("\\", "\\\\").replace('"', '\\"')[:400]
        script = f'display notification "{b}" with title "{t}" sound name "Glass"'
        try:
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)
        except Exception as e:
            log.debug("macOS notification failed: %s", e)

    def _webhook(self, title: str, body: str, alert: dict[str, Any]) -> None:
        url = self.settings.alert_webhook_url
        if not url:
            return
        payload = {
            "content": f"**{title}**\n{body}",
            "text": f"{title}\n{body}",
            "alert": alert,
        }
        try:
            with httpx.Client(timeout=15) as client:
                client.post(url, json=payload)
        except Exception as e:
            log.warning("Alert webhook failed: %s", e)
