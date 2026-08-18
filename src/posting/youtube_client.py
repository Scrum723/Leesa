"""YouTube Shorts / video upload via YouTube Data API v3."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import GeneratedContent, PostResult
from .base import PlatformClient

log = logging.getLogger("liaison.posting.youtube")


class YouTubeClient(PlatformClient):
    name = "youtube"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._youtube = None
        if self.is_configured() and not settings.dry_run:
            try:
                self._youtube = self._build_service()
            except Exception as e:
                log.error("YouTube client init failed: %s", e)

    def is_configured(self) -> bool:
        s = self.settings
        if s.youtube_client_secrets_file and Path(s.youtube_client_secrets_file).expanduser().exists():
            return True
        if s.youtube_token_file and Path(s.youtube_token_file).expanduser().exists():
            return True
        return bool(s.youtube_client_id and s.youtube_refresh_token)

    def _build_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]
        s = self.settings
        creds = None
        token_path = Path(s.youtube_token_file).expanduser() if s.youtube_token_file else None

        if token_path and token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        elif s.youtube_client_id and s.youtube_refresh_token:
            creds = Credentials(
                token=None,
                refresh_token=s.youtube_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=s.youtube_client_id,
                client_secret=s.youtube_client_secret,
                scopes=scopes,
            )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if token_path:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json(), encoding="utf-8")

        if not creds or not creds.valid:
            secrets = Path(s.youtube_client_secrets_file).expanduser()
            if not secrets.exists():
                raise RuntimeError("YouTube OAuth not configured — run auth flow once")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
            creds = flow.run_local_server(port=0)
            if token_path:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("youtube", "v3", credentials=creds)

    def post_video(self, video_path: Path, content: GeneratedContent) -> PostResult:
        if self.dry_run or not self.is_configured():
            if not self.is_configured() and not self.dry_run:
                return PostResult(platform=self.name, success=False, error="YouTube credentials missing")
            return self.dry_result(content, f"file={video_path.name}")

        if not self._youtube:
            try:
                self._youtube = self._build_service()
            except Exception as e:
                return PostResult(platform=self.name, success=False, error=str(e))

        from googleapiclient.http import MediaFileUpload

        title = content.title
        # Shorts convention: vertical + #Shorts helps discovery
        if "#shorts" not in title.lower() and "#shorts" not in content.description.lower():
            if len(title) < 90:
                title = f"{title} #Shorts"

        tags = [h.lstrip("#") for h in content.hashtags]
        desc = content.caption()
        if self.settings.linktree not in desc:
            desc = f"{desc}\n\n{self.settings.linktree}"

        privacy = self.cfg.get("privacy_status", "public")
        category = str(self.cfg.get("category_id", "28"))
        notify = bool(self.cfg.get("notify_subscribers", True))
        made_for_kids = bool(self.cfg.get("made_for_kids", False))

        body = {
            "snippet": {
                "title": title[:100],
                "description": desc[:4900],
                "tags": tags[:30],
                "categoryId": category,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": made_for_kids,
                "notifySubscribers": notify,
            },
        }

        try:
            media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/*")
            request = self._youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    log.info("YouTube upload progress %.0f%%", status.progress() * 100)
            vid = response.get("id", "")
            url = f"https://www.youtube.com/shorts/{vid}" if vid else ""
            log.info("YouTube uploaded: %s", url)
            return PostResult(
                platform=self.name,
                success=bool(vid),
                external_id=vid,
                url=url,
                raw=response or {},
            )
        except Exception as e:
            log.exception("YouTube post failed")
            return PostResult(platform=self.name, success=False, error=str(e))

    def notify_followers(self, content: GeneratedContent, post: PostResult) -> PostResult | None:
        # notifySubscribers is set at upload; community posts need separate API
        if not self.cfg.get("notify_subscribers", True):
            return None
        return PostResult(
            platform=self.name,
            success=True,
            external_id="notify_via_upload_flag",
            dry_run=self.dry_run,
            raw={"notify": True, "video": post.external_id},
        )

    def list_recent_comments(self, post_external_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if self.dry_run or not self._youtube or not post_external_id or post_external_id.startswith("dry_"):
            return []
        try:
            resp = (
                self._youtube.commentThreads()
                .list(part="snippet", videoId=post_external_id, maxResults=min(limit, 50), textFormat="plainText")
                .execute()
            )
            out = []
            for item in resp.get("items", []):
                sn = item["snippet"]["topLevelComment"]["snippet"]
                out.append(
                    {
                        "id": item["snippet"]["topLevelComment"]["id"],
                        "author": sn.get("authorDisplayName", ""),
                        "text": sn.get("textDisplay", ""),
                        "created_at": sn.get("publishedAt", ""),
                    }
                )
            return out
        except Exception as e:
            log.debug("YouTube comments: %s", e)
            return []

    def reply_to_comment(self, comment_id: str, text: str, post_external_id: str = "") -> bool:
        if self.dry_run:
            log.info("[DRY_RUN] YouTube reply to %s: %s", comment_id, text)
            return True
        if not self._youtube:
            return False
        try:
            self._youtube.comments().insert(
                part="snippet",
                body={"snippet": {"parentId": comment_id, "textOriginal": text}},
            ).execute()
            return True
        except Exception as e:
            log.warning("YouTube reply failed: %s", e)
            return False

    def fetch_metrics(self, post_external_id: str) -> dict[str, int]:
        if self.dry_run or not self._youtube or not post_external_id or post_external_id.startswith("dry_"):
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        try:
            resp = self._youtube.videos().list(part="statistics", id=post_external_id).execute()
            items = resp.get("items") or []
            if not items:
                return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
            st = items[0].get("statistics", {})
            return {
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "comments": int(st.get("commentCount", 0) or 0),
                "shares": 0,
                "saves": int(st.get("favoriteCount", 0) or 0),
            }
        except Exception as e:
            log.debug("YouTube metrics: %s", e)
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
