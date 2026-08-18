"""Instagram Reels via Meta Graph API (Business/Creator account)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..models import GeneratedContent, PostResult
from .base import PlatformClient

log = logging.getLogger("liaison.posting.instagram")

GRAPH = "https://graph.facebook.com/v21.0"


class InstagramClient(PlatformClient):
    name = "instagram"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    def is_configured(self) -> bool:
        return bool(
            self.settings.instagram_access_token and self.settings.instagram_business_account_id
        )

    def post_video(self, video_path: Path, content: GeneratedContent) -> PostResult:
        if self.dry_run or not self.is_configured():
            if not self.is_configured() and not self.dry_run:
                return PostResult(
                    platform=self.name,
                    success=False,
                    error="Instagram credentials missing (token + business account id)",
                )
            return self.dry_result(content, f"file={video_path.name}")

        # Graph API Reels require a publicly reachable video_url OR resumable upload.
        # For local files we use the resumable rupload path when available; otherwise
        # document that a hosted URL is needed. Here we attempt container create with
        # file upload helpers — if the API rejects local paths, return a clear error.
        token = self.settings.instagram_access_token
        ig_user = self.settings.instagram_business_account_id
        caption = content.caption()
        if len(caption) > 2200:
            caption = caption[:2197] + "…"

        try:
            # Preferred path: user hosts video (S3/CDN). Optional env override via path scheme.
            # For dry production setups without hosting, fail with actionable message.
            video_url = None
            if str(video_path).startswith("http"):
                video_url = str(video_path)

            if not video_url:
                # Attempt Instagram Content Publishing with upload session (Reels).
                # Meta's local file flow: upload to rupload.facebook.com then publish.
                container_id = self._create_reel_from_file(ig_user, token, video_path, caption)
            else:
                container_id = self._create_reel_from_url(ig_user, token, video_url, caption)

            if not container_id:
                return PostResult(
                    platform=self.name,
                    success=False,
                    error="Failed to create IG media container",
                )

            # Wait for processing
            if not self._wait_container(container_id, token):
                return PostResult(
                    platform=self.name,
                    success=False,
                    error="IG container processing timeout/failed",
                    external_id=container_id,
                )

            media_id = self._publish(ig_user, token, container_id)
            url = f"https://www.instagram.com/reel/{media_id}/" if media_id else ""
            return PostResult(
                platform=self.name,
                success=bool(media_id),
                external_id=media_id or container_id,
                url=url,
            )
        except Exception as e:
            log.exception("Instagram post failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def _create_reel_from_url(self, ig_user: str, token: str, video_url: str, caption: str) -> str:
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{GRAPH}/{ig_user}/media",
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": token,
                },
            )
            r.raise_for_status()
            return str(r.json().get("id", ""))

    def _create_reel_from_file(
        self, ig_user: str, token: str, video_path: Path, caption: str
    ) -> str:
        """
        Meta requires a public video_url for the simple path.
        We surface a clear error; production deploy should upload to temporary public storage first.
        """
        # Try phase: init upload session (some app types support this for Reels)
        size = video_path.stat().st_size
        with httpx.Client(timeout=180) as client:
            init = client.post(
                f"{GRAPH}/{ig_user}/media",
                data={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": caption,
                    "access_token": token,
                },
            )
            if init.status_code >= 400:
                raise RuntimeError(
                    "Instagram Reels need a publicly reachable video_url or resumable upload "
                    f"enabled on your Meta app. API said: {init.text[:300]}. "
                    "Workaround: host the file (S3/Cloudflare R2) and set path to https URL, "
                    "or use dry_run until hosting is wired."
                )
            data = init.json()
            container_id = str(data.get("id", ""))
            # If API returned upload_uri, push bytes
            upload_uri = data.get("uri") or data.get("upload_uri")
            if upload_uri:
                with video_path.open("rb") as f:
                    up = client.post(
                        upload_uri,
                        content=f.read(),
                        headers={
                            "Authorization": f"OAuth {token}",
                            "offset": "0",
                            "file_size": str(size),
                            "Content-Type": "application/octet-stream",
                        },
                    )
                    if up.status_code >= 400:
                        raise RuntimeError(f"IG rupload failed: {up.text[:300]}")
            return container_id

    def _wait_container(self, container_id: str, token: str, timeout: int = 300) -> bool:
        deadline = time.time() + timeout
        with httpx.Client(timeout=30) as client:
            while time.time() < deadline:
                r = client.get(
                    f"{GRAPH}/{container_id}",
                    params={"fields": "status_code,status", "access_token": token},
                )
                if r.status_code >= 400:
                    return False
                status = (r.json().get("status_code") or "").upper()
                if status == "FINISHED":
                    return True
                if status in {"ERROR", "EXPIRED"}:
                    log.error("IG container status: %s", r.json())
                    return False
                time.sleep(5)
        return False

    def _publish(self, ig_user: str, token: str, container_id: str) -> str:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                f"{GRAPH}/{ig_user}/media_publish",
                data={"creation_id": container_id, "access_token": token},
            )
            r.raise_for_status()
            return str(r.json().get("id", ""))

    def list_recent_comments(self, post_external_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if self.dry_run or not self.is_configured() or post_external_id.startswith("dry_"):
            return []
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(
                    f"{GRAPH}/{post_external_id}/comments",
                    params={
                        "fields": "id,text,username,timestamp",
                        "limit": min(limit, 50),
                        "access_token": self.settings.instagram_access_token,
                    },
                )
                r.raise_for_status()
                out = []
                for c in r.json().get("data", []):
                    out.append(
                        {
                            "id": c.get("id"),
                            "author": c.get("username", ""),
                            "text": c.get("text", ""),
                            "created_at": c.get("timestamp", ""),
                        }
                    )
                return out
        except Exception as e:
            log.debug("IG comments: %s", e)
            return []

    def reply_to_comment(self, comment_id: str, text: str, post_external_id: str = "") -> bool:
        if self.dry_run or not self.is_configured():
            log.info("[DRY_RUN] IG reply to %s: %s", comment_id, text)
            return True
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    f"{GRAPH}/{comment_id}/replies",
                    data={
                        "message": text,
                        "access_token": self.settings.instagram_access_token,
                    },
                )
                r.raise_for_status()
                return True
        except Exception as e:
            log.warning("IG reply failed: %s", e)
            return False

    def fetch_metrics(self, post_external_id: str) -> dict[str, int]:
        if self.dry_run or not self.is_configured() or post_external_id.startswith("dry_"):
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(
                    f"{GRAPH}/{post_external_id}/insights",
                    params={
                        "metric": "plays,likes,comments,shares,saved",
                        "access_token": self.settings.instagram_access_token,
                    },
                )
                if r.status_code >= 400:
                    return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
                metrics = {d["name"]: d.get("values", [{}])[0].get("value", 0) for d in r.json().get("data", [])}
                return {
                    "views": int(metrics.get("plays", 0) or 0),
                    "likes": int(metrics.get("likes", 0) or 0),
                    "comments": int(metrics.get("comments", 0) or 0),
                    "shares": int(metrics.get("shares", 0) or 0),
                    "saves": int(metrics.get("saved", 0) or 0),
                }
        except Exception as e:
            log.debug("IG metrics: %s", e)
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}

    def notify_followers(self, content: GeneratedContent, post: PostResult) -> PostResult | None:
        # Stories API requires image/video assets; log CTA for manual or future story post
        if not self.cfg.get("notify_followers", True):
            return None
        log.info(
            "IG fan notify (story CTA): %s | post=%s",
            content.notify_text or content.title,
            post.url,
        )
        return PostResult(
            platform=self.name,
            success=True,
            external_id="notify_logged",
            dry_run=self.dry_run,
            raw={"notify": content.notify_text, "post_url": post.url},
        )
