"""Coordinate multi-platform posting for one video job."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from .. import db
from ..ai_content import ContentGenerator
from ..config import ROOT, Settings
from ..logging_setup import EventLog
from ..models import GeneratedContent, JobStatus, PostResult, utcnow
from .instagram_client import InstagramClient
from .tiktok_client import TikTokClient
from .x_client import XClient
from .youtube_client import YouTubeClient

log = logging.getLogger("liaison.posting.orchestrator")


class PostingOrchestrator:
    def __init__(self, settings: Settings, events: EventLog | None = None) -> None:
        self.settings = settings
        self.events = events or EventLog()
        self.content_gen = ContentGenerator(settings)
        self.clients = {
            "x": XClient(settings),
            "instagram": InstagramClient(settings),
            "tiktok": TikTokClient(settings),
            "youtube": YouTubeClient(settings),
        }

    def active_platforms(self) -> list[str]:
        out = []
        for name, client in self.clients.items():
            if not self.settings.is_platform_enabled(name):
                continue
            overlay = db.get_platform_settings(name)
            if overlay.get("enabled") is False:
                continue
            out.append(name)
        return out

    def process_job(self, job: dict[str, Any], force: bool = False) -> dict[str, Any]:
        job_id = int(job["id"])
        path = Path(job["path"])
        if not path.exists():
            db.update_job(job_id, status=JobStatus.FAILED.value, error=f"File missing: {path}")
            self.events.write("post_failed", job_id=job_id, error="file_missing")
            return {"ok": False, "error": "file_missing"}

        watcher_cfg = self.settings.config.get("watcher") or {}
        max_day = int(watcher_cfg.get("max_posts_per_day") or 0)
        if not force and max_day > 0 and db.posts_today_count() >= max_day:
            log.info("Daily post cap reached (%s); leaving job %s queued", max_day, job_id)
            return {"ok": False, "error": "daily_cap", "deferred": True}

        platforms = self.active_platforms()
        if not platforms:
            db.update_job(job_id, status=JobStatus.FAILED.value, error="No platforms enabled")
            return {"ok": False, "error": "no_platforms"}

        db.update_job(job_id, status=JobStatus.GENERATING.value)
        content_map = self.content_gen.generate_for_video(path, platforms=platforms)
        content_json = {k: v.to_dict() for k, v in content_map.items()}
        db.update_job(job_id, content_json=json.dumps(content_json), status=JobStatus.POSTING.value)
        self.events.write("content_generated", job_id=job_id, platforms=platforms)

        results: list[PostResult] = []
        for platform in platforms:
            client = self.clients[platform]
            content = content_map.get(platform) or GeneratedContent(
                platform=platform, title=path.stem, description=path.stem
            )
            # Merge dashboard overlay reply settings into client cfg view if needed
            try:
                result = client.post_video(path, content)
            except Exception as e:
                log.exception("Unhandled post error on %s", platform)
                result = PostResult(platform=platform, success=False, error=str(e))
            results.append(result)

            db.insert_post(
                job_id=job_id,
                platform=platform,
                external_id=result.external_id,
                url=result.url,
                title=content.title,
                description=content.description,
                hashtags=content.hashtags,
                status="posted" if result.success else "failed",
                raw=result.raw,
            )
            self.events.write(
                "platform_post",
                job_id=job_id,
                platform=platform,
                success=result.success,
                external_id=result.external_id,
                url=result.url,
                error=result.error,
            )

            if result.success:
                try:
                    client.notify_followers(content, result)
                except Exception as e:
                    log.warning("Notify failed on %s: %s", platform, e)
            else:
                db.create_alert(
                    severity="error",
                    category="error",
                    title=f"Post failed on {platform}",
                    body=result.error or "unknown",
                    platform=platform,
                )

        successes = sum(1 for r in results if r.success)
        if successes == len(results):
            status = JobStatus.POSTED.value
        elif successes > 0:
            status = JobStatus.PARTIAL.value
        else:
            status = JobStatus.FAILED.value

        db.update_job(
            job_id,
            status=status,
            posted_at=utcnow() if successes else None,
            results_json=json.dumps([r.to_dict() for r in results]),
            error="" if successes else "all platforms failed",
        )

        if successes:
            self._archive(path, watcher_cfg)

        self.events.write(
            "job_complete",
            job_id=job_id,
            status=status,
            successes=successes,
            total=len(results),
        )
        return {
            "ok": successes > 0,
            "status": status,
            "results": [r.to_dict() for r in results],
        }

    def process_next_queued(self, force: bool = False) -> dict[str, Any] | None:
        job = db.next_queued_job()
        if not job:
            return None
        return self.process_job(job, force=force)

    def process_content_item(self, item: dict[str, Any], force: bool = False) -> dict[str, Any]:
        """Post a library item: video, article, or bundle (video + writing)."""
        kind = item.get("kind") or "video"
        platforms = list(item.get("platforms") or []) or self.active_platforms()
        platforms = [p for p in platforms if p in self.clients and self.settings.is_platform_enabled(p)]
        if not platforms:
            platforms = self.active_platforms()
        if not platforms:
            return {"ok": False, "error": "no_platforms"}

        title_hint = item.get("title_hint") or "Doc Weather update"
        body = item.get("body") or ""
        video_path = Path(item["video_path"]) if item.get("video_path") else None
        hint = f"{title_hint}\n\n{body}".strip() if body else title_hint

        # Generate captions; seed with user's writing when present
        if video_path and video_path.exists():
            content_map = self.content_gen.generate_for_video(
                video_path, platforms=platforms, hint=hint[:1500]
            )
        else:
            # Article-only: synthesize GeneratedContent from writing
            content_map = {}
            for p in platforms:
                fallback = self.content_gen._fallback(p, title_hint)
                if body:
                    fallback.description = body[: self.settings.config.get("content", {}).get("description_max_chars", {}).get(p, 2000)]
                    fallback.title = title_hint[:100]
                    fallback.notify_text = f"New from {self.settings.streamer_name}: {title_hint} → {self.settings.linktree}"
                content_map[p] = fallback
            # Optional AI polish when key available
            if self.content_gen.available and body:
                try:
                    polished = self.content_gen.generate_for_video(
                        Path(title_hint.replace("/", "-") + ".md"),
                        platforms=platforms,
                        hint=hint[:2000],
                    )
                    content_map = polished
                except Exception:
                    pass

        # If user wrote insight, prefer body as description base on long-form platforms
        if body:
            for p, gen in content_map.items():
                if p in ("instagram", "youtube", "tiktok") and len(body) > 40:
                    # Prepend user insight, keep AI title/hashtags
                    gen.description = body.strip()
                    if self.settings.linktree not in gen.description:
                        gen.description = f"{gen.description}\n\n{self.settings.linktree}"

        results: list[PostResult] = []
        for platform in platforms:
            client = self.clients[platform]
            content = content_map.get(platform) or GeneratedContent(
                platform=platform, title=title_hint, description=body or title_hint
            )
            try:
                if video_path and video_path.exists() and kind in ("video", "bundle"):
                    result = client.post_video(video_path, content)
                else:
                    result = client.post_text(content)
            except Exception as e:
                log.exception("post failed %s", platform)
                result = PostResult(platform=platform, success=False, error=str(e))
            results.append(result)
            db.insert_post(
                job_id=None,
                platform=platform,
                external_id=result.external_id,
                url=result.url,
                title=content.title,
                description=content.description,
                hashtags=content.hashtags,
                status="posted" if result.success else "failed",
                raw={**result.raw, "kind": kind, "source_path": item.get("path")},
            )
            if result.success:
                try:
                    client.notify_followers(content, result)
                except Exception:
                    pass

        ok = any(r.success for r in results)
        if ok:
            try:
                from ..content_library import ContentItem, archive_item

                archive_item(
                    ContentItem(
                        kind=kind,
                        path=item.get("path") or "",
                        title_hint=title_hint,
                        body=body,
                        video_path=item.get("video_path") or "",
                        article_path=item.get("article_path") or "",
                        status_folder=item.get("status_folder") or "ready",
                    )
                )
            except Exception as e:
                log.warning("archive item: %s", e)
            if item.get("path"):
                db.update_content_item(item["path"], job_status="posted", status_folder="posted")
        self.events.write(
            "content_item_post",
            kind=kind,
            path=item.get("path"),
            ok=ok,
            platforms=platforms,
        )
        return {"ok": ok, "results": [r.to_dict() for r in results], "kind": kind}

    def _archive(self, path: Path, watcher_cfg: dict[str, Any]) -> None:
        rel = watcher_cfg.get("archive_dir") or "data/posted"
        dest_dir = ROOT / rel
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        try:
            if path.resolve() != dest.resolve() and path.exists():
                shutil.move(str(path), str(dest))
                log.info("Archived video to %s", dest)
        except Exception as e:
            log.warning("Archive failed for %s: %s", path, e)
