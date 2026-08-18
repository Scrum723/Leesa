"""Shared data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Platform(str, Enum):
    X = "x"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class JobStatus(str, Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    POSTING = "posting"
    POSTED = "posted"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GeneratedContent:
    platform: str
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)
    notify_text: str = ""

    def caption(self) -> str:
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in self.hashtags)
        parts = [self.description.strip()]
        if tags:
            parts.append(tags)
        return "\n\n".join(p for p in parts if p).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostResult:
    platform: str
    success: bool
    external_id: str = ""
    url: str = ""
    error: str = ""
    dry_run: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoJob:
    id: int | None
    path: str
    filename: str
    status: str = JobStatus.QUEUED.value
    discovered_at: str = field(default_factory=utcnow)
    scheduled_for: str | None = None
    posted_at: str | None = None
    content_json: str = "{}"
    results_json: str = "[]"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Comment:
    platform: str
    external_id: str
    post_external_id: str
    author: str
    text: str
    created_at: str = ""
    reply_to: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngagementMetrics:
    platform: str
    post_external_id: str
    job_id: int | None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    fetched_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
