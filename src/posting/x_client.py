"""X (Twitter) video posting via tweepy / API v2 media upload."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import GeneratedContent, PostResult
from .base import PlatformClient

log = logging.getLogger("liaison.posting.x")


def _chunk_tweet(text: str, hashtags: list[str] | None = None) -> list[str]:
    tags = " ".join(hashtags or [])
    # First chunk can include light hashtags
    limit = 270
    parts: list[str] = []
    remaining = (text or "").strip()
    if not remaining:
        remaining = "Update from Doc Weather"
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        cut = remaining.rfind(" ", 0, limit)
        if cut < 40:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if tags and parts:
        candidate = f"{parts[0]}\n\n{tags}".strip()
        if len(candidate) <= 280:
            parts[0] = candidate
    return parts or [text[:270]]


class XClient(PlatformClient):
    name = "x"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._api = None
        self._client = None
        if self.is_configured():
            try:
                import tweepy

                auth = tweepy.OAuth1UserHandler(
                    settings.x_api_key,
                    settings.x_api_secret,
                    settings.x_access_token,
                    settings.x_access_token_secret,
                )
                self._api = tweepy.API(auth, wait_on_rate_limit=True)
                self._client = tweepy.Client(
                    consumer_key=settings.x_api_key,
                    consumer_secret=settings.x_api_secret,
                    access_token=settings.x_access_token,
                    access_token_secret=settings.x_access_token_secret,
                    wait_on_rate_limit=True,
                )
            except Exception as e:
                log.error("Failed to init X client: %s", e)

    def is_configured(self) -> bool:
        s = self.settings
        return bool(s.x_api_key and s.x_api_secret and s.x_access_token and s.x_access_token_secret)

    def post_video(self, video_path: Path, content: GeneratedContent) -> PostResult:
        if self.dry_run or not self._api or not self._client:
            if not self.is_configured() and not self.dry_run:
                return PostResult(platform=self.name, success=False, error="X credentials missing")
            return self.dry_result(content, f"file={video_path.name}")

        try:
            media = self._api.media_upload(
                filename=str(video_path),
                media_category="tweet_video",
                chunked=True,
            )
            text = content.caption()
            # X hard limit ~280; keep room for media
            if len(text) > 270:
                text = text[:267].rstrip() + "…"
            resp = self._client.create_tweet(text=text, media_ids=[media.media_id])
            tweet_id = ""
            if resp and getattr(resp, "data", None):
                tweet_id = str(resp.data.get("id", ""))
            url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
            log.info("Posted to X: %s", url or tweet_id)
            return PostResult(
                platform=self.name,
                success=True,
                external_id=tweet_id,
                url=url,
                raw={"media_id": getattr(media, "media_id", None)},
            )
        except Exception as e:
            log.exception("X post failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def post_text(self, content: GeneratedContent) -> PostResult:
        """Article / insight as tweet or short thread."""
        if self.dry_run or not self._client:
            if not self.is_configured() and not self.dry_run:
                return PostResult(platform=self.name, success=False, error="X credentials missing")
            return self.dry_result(content, note="text_only")

        # Prefer title + first part of description
        body = content.caption() if content.description else content.title
        chunks = _chunk_tweet(body, content.hashtags)
        try:
            first_id = ""
            prev_id = None
            for i, chunk in enumerate(chunks[:6]):
                kwargs: dict[str, Any] = {"text": chunk}
                if prev_id:
                    kwargs["in_reply_to_tweet_id"] = prev_id
                resp = self._client.create_tweet(**kwargs)
                tid = ""
                if resp and getattr(resp, "data", None):
                    tid = str(resp.data.get("id", ""))
                if i == 0:
                    first_id = tid
                prev_id = tid
            url = f"https://x.com/i/status/{first_id}" if first_id else ""
            return PostResult(
                platform=self.name,
                success=bool(first_id),
                external_id=first_id,
                url=url,
                raw={"chunks": len(chunks)},
            )
        except Exception as e:
            log.exception("X text post failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def create_poll(
        self,
        text: str,
        options: list[str],
        duration_minutes: int = 1440,
    ) -> PostResult:
        """Create an organic X post with a native poll (OAuth 1.0a user context)."""
        opts = [str(o).strip()[:25] for o in options if str(o).strip()][:4]
        if len(opts) < 2:
            return PostResult(platform=self.name, success=False, error="Need at least 2 poll options")
        duration_minutes = max(5, min(int(duration_minutes), 10080))
        text = (text or "").strip()
        if len(text) > 280:
            text = text[:277].rstrip() + "…"

        if self.dry_run or not self._client:
            if not self.is_configured() and not self.dry_run:
                return PostResult(platform=self.name, success=False, error="X credentials missing")
            log.info("[DRY_RUN] X poll: %s | options=%s | %sm", text, opts, duration_minutes)
            return PostResult(
                platform=self.name,
                success=True,
                external_id="dry_poll_x",
                url="https://example.local/dry/x-poll",
                dry_run=True,
                raw={"options": opts, "duration_minutes": duration_minutes, "text": text},
            )

        try:
            resp = self._client.create_tweet(
                text=text,
                poll_options=opts,
                poll_duration_minutes=duration_minutes,
            )
            tweet_id = ""
            if resp and getattr(resp, "data", None):
                tweet_id = str(resp.data.get("id", ""))
            url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
            log.info("Posted X poll: %s", url or tweet_id)
            return PostResult(
                platform=self.name,
                success=bool(tweet_id),
                external_id=tweet_id,
                url=url,
                raw={"options": opts, "duration_minutes": duration_minutes},
            )
        except Exception as e:
            log.exception("X poll create failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def fetch_poll_results(self, tweet_id: str) -> dict[str, Any]:
        """Fetch poll options + vote counts for a tweet."""
        if not tweet_id or tweet_id.startswith("dry_"):
            return {"ok": True, "options": [], "total_votes": 0, "note": "dry_run"}
        if self.dry_run or not self._client:
            return {"ok": True, "options": [], "total_votes": 0, "note": "dry_run_or_no_client"}
        try:
            resp = self._client.get_tweet(
                tweet_id,
                expansions=["attachments.poll_ids"],
                poll_fields=["options", "voting_status", "end_datetime", "duration_minutes"],
            )
            includes = getattr(resp, "includes", None) or {}
            polls = includes.get("polls") if isinstance(includes, dict) else None
            if not polls and hasattr(includes, "get"):
                polls = includes.get("polls")
            # tweepy may return objects
            poll_list = polls or []
            if not poll_list:
                # Fallback raw
                data = getattr(resp, "data", None)
                return {
                    "ok": False,
                    "error": "No poll attachment on tweet",
                    "raw": str(data)[:300],
                }
            poll = poll_list[0]
            raw_opts = getattr(poll, "options", None) or (poll.get("options") if isinstance(poll, dict) else [])
            options = []
            total = 0
            for i, o in enumerate(raw_opts or []):
                if isinstance(o, dict):
                    label = o.get("label", "")
                    votes = int(o.get("votes", 0) or 0)
                    position = int(o.get("position", i) or i)
                else:
                    label = getattr(o, "label", "")
                    votes = int(getattr(o, "votes", 0) or 0)
                    position = int(getattr(o, "position", i) or i)
                total += votes
                options.append({"label": label, "votes": votes, "position": position})
            return {
                "ok": True,
                "options": options,
                "total_votes": total,
                "voting_status": getattr(poll, "voting_status", None)
                or (poll.get("voting_status") if isinstance(poll, dict) else None),
            }
        except Exception as e:
            log.warning("X poll results failed: %s", e)
            return {"ok": False, "error": str(e)}

    def notify_followers(self, content: GeneratedContent, post: PostResult) -> PostResult | None:
        if not self.cfg.get("notify_followers", True):
            return None
        text = content.notify_text or f"New video 🎥 {content.title}\n{self.settings.linktree}"
        if post.url and post.url not in text:
            text = f"{text}\n{post.url}"
        if len(text) > 280:
            text = text[:277] + "…"
        if self.dry_run or not self._client:
            log.info("[DRY_RUN] X notify: %s", text)
            return PostResult(
                platform=self.name,
                success=True,
                external_id="dry_notify",
                dry_run=True,
                raw={"text": text},
            )
        try:
            kwargs: dict[str, Any] = {"text": text}
            if post.external_id:
                kwargs["quote_tweet_id"] = post.external_id
            resp = self._client.create_tweet(**kwargs)
            tid = str(resp.data.get("id", "")) if resp and resp.data else ""
            return PostResult(
                platform=self.name,
                success=True,
                external_id=tid,
                url=f"https://x.com/i/status/{tid}" if tid else "",
            )
        except Exception as e:
            log.warning("X notify failed: %s", e)
            return PostResult(platform=self.name, success=False, error=str(e))

    def list_recent_comments(self, post_external_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if self.dry_run or not self._client or not post_external_id or post_external_id.startswith("dry_"):
            return []
        try:
            # Search recent replies mentioning conversation — best-effort
            query = f"conversation_id:{post_external_id}"
            resp = self._client.search_recent_tweets(
                query=query,
                max_results=min(limit, 100),
                tweet_fields=["author_id", "created_at", "conversation_id"],
            )
            out = []
            for t in resp.data or []:
                out.append(
                    {
                        "id": str(t.id),
                        "author": str(getattr(t, "author_id", "")),
                        "text": t.text,
                        "created_at": str(getattr(t, "created_at", "")),
                    }
                )
            return out
        except Exception as e:
            log.debug("X list comments: %s", e)
            return []

    def reply_to_comment(self, comment_id: str, text: str, post_external_id: str = "") -> bool:
        if self.dry_run or not self._client:
            log.info("[DRY_RUN] X reply to %s: %s", comment_id, text)
            return True
        try:
            self._client.create_tweet(text=text, in_reply_to_tweet_id=comment_id)
            return True
        except Exception as e:
            log.warning("X reply failed: %s", e)
            return False

    def fetch_metrics(self, post_external_id: str) -> dict[str, int]:
        if self.dry_run or not self._client or not post_external_id or post_external_id.startswith("dry_"):
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        try:
            resp = self._client.get_tweet(
                post_external_id,
                tweet_fields=["public_metrics"],
            )
            m = (resp.data.public_metrics if resp and resp.data else {}) or {}
            return {
                "views": int(m.get("impression_count", 0) or 0),
                "likes": int(m.get("like_count", 0) or 0),
                "comments": int(m.get("reply_count", 0) or 0),
                "shares": int(m.get("retweet_count", 0) or 0) + int(m.get("quote_count", 0) or 0),
                "saves": int(m.get("bookmark_count", 0) or 0),
            }
        except Exception as e:
            log.debug("X metrics: %s", e)
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
