"""TikTok Content Posting API client (inbox/direct post)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..models import GeneratedContent, PostResult
from .base import PlatformClient

log = logging.getLogger("liaison.posting.tiktok")

API = "https://open.tiktokapis.com/v2"


class TikTokClient(PlatformClient):
    name = "tiktok"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    def is_configured(self) -> bool:
        return bool(self.settings.tiktok_access_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.tiktok_access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def post_video(self, video_path: Path, content: GeneratedContent) -> PostResult:
        if self.dry_run or not self.is_configured():
            if not self.is_configured() and not self.dry_run:
                return PostResult(platform=self.name, success=False, error="TikTok access token missing")
            return self.dry_result(content, f"file={video_path.name}")

        caption = content.caption()
        if len(caption) > 2200:
            caption = caption[:2197] + "…"

        privacy = self.cfg.get("privacy_level", "PUBLIC_TO_EVERYONE")
        size = video_path.stat().st_size

        try:
            with httpx.Client(timeout=180) as client:
                # 1) Init upload
                init = client.post(
                    f"{API}/post/publish/video/init/",
                    headers=self._headers(),
                    json={
                        "post_info": {
                            "title": caption[:150],
                            "privacy_level": privacy,
                            "disable_duet": bool(self.cfg.get("disable_duet", False)),
                            "disable_comment": bool(self.cfg.get("disable_comment", False)),
                            "disable_stitch": bool(self.cfg.get("disable_stitch", False)),
                            "video_cover_timestamp_ms": 1000,
                        },
                        "source_info": {
                            "source": "FILE_UPLOAD",
                            "video_size": size,
                            "chunk_size": size,
                            "total_chunk_count": 1,
                        },
                    },
                )
                if init.status_code >= 400:
                    return PostResult(
                        platform=self.name,
                        success=False,
                        error=f"TikTok init failed: {init.text[:400]}",
                    )
                body = init.json().get("data") or {}
                publish_id = str(body.get("publish_id", ""))
                upload_url = body.get("upload_url", "")
                if not upload_url:
                    return PostResult(
                        platform=self.name,
                        success=False,
                        error=f"No upload_url in TikTok response: {init.text[:300]}",
                    )

                # 2) Upload binary
                with video_path.open("rb") as f:
                    raw = f.read()
                up = client.put(
                    upload_url,
                    content=raw,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(size),
                        "Content-Range": f"bytes 0-{size - 1}/{size}",
                    },
                )
                if up.status_code >= 400:
                    return PostResult(
                        platform=self.name,
                        success=False,
                        error=f"TikTok upload failed: {up.text[:300]}",
                    )

                log.info("TikTok publish initiated publish_id=%s", publish_id)
                return PostResult(
                    platform=self.name,
                    success=True,
                    external_id=publish_id,
                    url="",  # final share URL available after processing via status endpoint
                    raw={"publish_id": publish_id},
                )
        except Exception as e:
            log.exception("TikTok post failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def notify_followers(self, content: GeneratedContent, post: PostResult) -> PostResult | None:
        if not self.cfg.get("notify_followers", True):
            return None
        log.info("TikTok fan notify logged: %s", content.notify_text or content.title)
        return PostResult(
            platform=self.name,
            success=True,
            external_id="notify_logged",
            dry_run=self.dry_run,
            raw={"notify": content.notify_text},
        )

    def list_recent_comments(self, post_external_id: str, limit: int = 50) -> list[dict[str, Any]]:
        # Comment list requires Research/special product access on many apps
        if self.dry_run or not self.is_configured() or post_external_id.startswith("dry_"):
            return []
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    f"{API}/video/comment/list/",
                    headers=self._headers(),
                    json={"video_id": post_external_id, "max_count": min(limit, 50)},
                )
                if r.status_code >= 400:
                    log.debug("TikTok comments unavailable: %s", r.text[:200])
                    return []
                out = []
                for c in (r.json().get("data") or {}).get("comments") or []:
                    out.append(
                        {
                            "id": str(c.get("id") or c.get("comment_id", "")),
                            "author": str(c.get("username") or c.get("user_id", "")),
                            "text": c.get("text", ""),
                            "created_at": str(c.get("create_time", "")),
                        }
                    )
                return out
        except Exception as e:
            log.debug("TikTok comments: %s", e)
            return []

    def reply_to_comment(self, comment_id: str, text: str, post_external_id: str = "") -> bool:
        if self.dry_run or not self.is_configured():
            log.info("[DRY_RUN] TikTok reply to %s: %s", comment_id, text)
            return True
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    f"{API}/video/comment/reply/create/",
                    headers=self._headers(),
                    json={
                        "video_id": post_external_id,
                        "comment_id": comment_id,
                        "text": text[:150],
                    },
                )
                return r.status_code < 400
        except Exception as e:
            log.warning("TikTok reply failed: %s", e)
            return False

    def fetch_metrics(self, post_external_id: str) -> dict[str, int]:
        if self.dry_run or not self.is_configured() or post_external_id.startswith("dry_"):
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    f"{API}/video/query/",
                    headers=self._headers(),
                    json={
                        "filters": {"video_ids": [post_external_id]},
                        "fields": [
                            "id",
                            "like_count",
                            "comment_count",
                            "share_count",
                            "view_count",
                        ],
                    },
                )
                if r.status_code >= 400:
                    return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
                videos = (r.json().get("data") or {}).get("videos") or []
                if not videos:
                    return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
                v = videos[0]
                return {
                    "views": int(v.get("view_count", 0) or 0),
                    "likes": int(v.get("like_count", 0) or 0),
                    "comments": int(v.get("comment_count", 0) or 0),
                    "shares": int(v.get("share_count", 0) or 0),
                    "saves": 0,
                }
        except Exception as e:
            log.debug("TikTok metrics: %s", e)
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
