"""Poll comments across platforms, auto-reply, raise important alerts."""

from __future__ import annotations

import logging
import re
from typing import Any

from .. import db
from ..ai_content import ContentGenerator
from ..config import Settings
from ..logging_setup import EventLog
from ..posting.orchestrator import PostingOrchestrator

log = logging.getLogger("liaison.engagement")

NEGATIVE = re.compile(
    r"\b(scam|fake|liar|stupid|hate|idiot|worst|trash|fraud)\b",
    re.I,
)


class EngagementMonitor:
    def __init__(
        self,
        settings: Settings,
        orchestrator: PostingOrchestrator | None = None,
        events: EventLog | None = None,
    ) -> None:
        self.settings = settings
        self.orch = orchestrator or PostingOrchestrator(settings)
        self.events = events or EventLog()
        self.ai = ContentGenerator(settings)
        self._user_last_reply: dict[str, float] = {}

    def run_once(self) -> dict[str, int]:
        if not self.settings.auto_engage_enabled:
            return {"skipped": 1}
        stats = {"comments_seen": 0, "replies": 0, "alerts": 0}
        posts = db.list_posts(limit=40)
        eng_cfg = self.settings.config.get("engagement") or {}
        cooldown = float(eng_cfg.get("cooldown_seconds_per_user", 300))
        min_len = int(eng_cfg.get("min_comment_length", 2))
        require_kw = bool(eng_cfg.get("require_keyword_match", False))

        for post in posts:
            platform = post["platform"]
            ext_id = post.get("external_id") or ""
            if not ext_id or ext_id.startswith("dry_"):
                continue
            client = self.orch.clients.get(platform)
            if not client:
                continue
            overlay = db.get_platform_settings(platform)
            pcfg = {**self.settings.platform_cfg(platform), **overlay}
            if not pcfg.get("reply_to_comments", True):
                continue
            reply_mode = pcfg.get("reply_mode", "ai")
            if reply_mode == "off":
                continue

            try:
                comments = client.list_recent_comments(ext_id)
            except Exception as e:
                log.debug("Comment poll %s: %s", platform, e)
                continue

            keywords = [k.lower() for k in (pcfg.get("engage_keywords") or [])]
            ignore = {u.lower() for u in (pcfg.get("ignore_users") or [])}

            for c in comments:
                cid = str(c.get("id") or "")
                author = str(c.get("author") or "user")
                text = str(c.get("text") or "").strip()
                if not cid or len(text) < min_len:
                    continue
                if author.lower() in ignore:
                    continue

                is_new = db.mark_comment_seen(platform, cid, ext_id, author, text)
                if not is_new:
                    continue
                stats["comments_seen"] += 1
                self.events.write(
                    "comment_seen",
                    platform=platform,
                    comment_id=cid,
                    author=author,
                    text=text[:200],
                )

                # Alerts
                if NEGATIVE.search(text):
                    db.create_alert(
                        severity="warning",
                        category="negative_sentiment",
                        title=f"Negative comment on {platform}",
                        body=f"@{author}: {text[:300]}",
                        platform=platform,
                    )
                    stats["alerts"] += 1

                if require_kw and keywords:
                    if not any(k in text.lower() for k in keywords):
                        continue

                # Rate limit per user
                import time

                key = f"{platform}:{author.lower()}"
                now = time.time()
                last = self._user_last_reply.get(key, 0)
                if now - last < cooldown:
                    continue

                reply_text = None
                if reply_mode == "ai":
                    reply_text = self.ai.reply_to_comment(
                        platform=platform,
                        author=author,
                        comment=text,
                        post_title=post.get("title") or "",
                    )
                elif reply_mode == "template":
                    reply_text = (
                        f"Thanks @{author}! Full links → {self.settings.linktree} "
                        f"— {self.settings.streamer_name}"
                    )

                if not reply_text:
                    continue

                ok = client.reply_to_comment(cid, reply_text, post_external_id=ext_id)
                if ok:
                    stats["replies"] += 1
                    self._user_last_reply[key] = now
                    # Update replied flag (re-insert ignored by unique; simple update)
                    with db.get_db() as conn:
                        conn.execute(
                            "UPDATE comments_seen SET replied = 1, reply_text = ? WHERE platform = ? AND external_id = ?",
                            (reply_text, platform, cid),
                        )
                    self.events.write(
                        "comment_reply",
                        platform=platform,
                        comment_id=cid,
                        reply=reply_text[:200],
                    )

        return stats

    def check_high_engagement(self) -> int:
        """Compare latest metrics vs thresholds and alert."""
        eng = self.settings.config.get("engagement") or {}
        thr = eng.get("high_engagement_threshold") or {}
        comments_thr = int(thr.get("comments_1h", 25))
        likes_thr = int(thr.get("likes_1h", 200))
        alerts = 0
        posts = db.list_posts(limit=20)
        for post in posts:
            platform = post["platform"]
            ext_id = post.get("external_id") or ""
            if not ext_id or ext_id.startswith("dry_"):
                continue
            client = self.orch.clients.get(platform)
            if not client:
                continue
            try:
                m = client.fetch_metrics(ext_id)
            except Exception:
                continue
            db.insert_metrics(
                platform=platform,
                post_external_id=ext_id,
                job_id=post.get("job_id"),
                views=m.get("views", 0),
                likes=m.get("likes", 0),
                comments=m.get("comments", 0),
                shares=m.get("shares", 0),
                saves=m.get("saves", 0),
            )
            if m.get("comments", 0) >= comments_thr or m.get("likes", 0) >= likes_thr:
                db.create_alert(
                    severity="info",
                    category="high_engagement",
                    title=f"High engagement on {platform}",
                    body=f"likes={m.get('likes')} comments={m.get('comments')} views={m.get('views')} id={ext_id}",
                    platform=platform,
                )
                alerts += 1
        return alerts
