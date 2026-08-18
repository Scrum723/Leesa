"""Base platform client interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import GeneratedContent, PostResult

log = logging.getLogger("liaison.posting")


class PlatformClient(ABC):
    name: str = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def dry_run(self) -> bool:
        return self.settings.dry_run

    @property
    def cfg(self) -> dict[str, Any]:
        base = self.settings.platform_cfg(self.name)
        # Dashboard overlay merged at runtime by orchestrator if provided
        return base

    def is_configured(self) -> bool:
        return False

    @abstractmethod
    def post_video(self, video_path: Path, content: GeneratedContent) -> PostResult:
        ...

    def post_text(self, content: GeneratedContent) -> PostResult:
        """Text-only / article post. Default: dry-run style not implemented."""
        if self.dry_run:
            return self.dry_result(content, note="text_only")
        return PostResult(
            platform=self.name,
            success=False,
            error=f"{self.name} text-only posts not implemented",
        )

    def notify_followers(self, content: GeneratedContent, post: PostResult) -> PostResult | None:
        """Optional follow-up notify post. Default: no-op."""
        return None

    def list_recent_comments(self, post_external_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def reply_to_comment(self, comment_id: str, text: str, post_external_id: str = "") -> bool:
        return False

    def fetch_metrics(self, post_external_id: str) -> dict[str, int]:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}

    def dry_result(self, content: GeneratedContent, note: str = "") -> PostResult:
        log.info(
            "[DRY_RUN] %s would post title=%r hashtags=%s %s",
            self.name,
            content.title,
            content.hashtags,
            note,
        )
        return PostResult(
            platform=self.name,
            success=True,
            external_id=f"dry_{self.name}_{content.title[:20]}",
            url=f"https://example.local/dry/{self.name}",
            dry_run=True,
            raw={"note": note or "dry_run"},
        )
