"""Scan the Doc Weather content library: videos, articles, bundles."""

from __future__ import annotations

import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("liaison.content")

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
ARTICLE_EXTS = {".md", ".txt", ".markdown"}


@dataclass
class ContentItem:
    kind: str  # video | article | bundle
    path: str
    title_hint: str
    body: str = ""
    video_path: str = ""
    article_path: str = ""
    platforms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status_folder: str = "ready"  # inbox | ready | posted
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_library_root() -> Path:
    return Path.home() / "Desktop" / "Doc Weather Content"


def ensure_library(root: Path | None = None) -> Path:
    root = root or default_library_root()
    for rel in (
        "videos/inbox",
        "videos/ready",
        "videos/posted",
        "articles/inbox",
        "articles/ready",
        "articles/posted",
        "bundles",
        "assets",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)

    template = root / "bundles" / "_TEMPLATE"
    template.mkdir(parents=True, exist_ok=True)
    insight = template / "insight.md"
    if not insight.exists():
        insight.write_text(
            "# Title of your insight\n\n"
            "Hook in the first sentence.\n\n"
            "Your personal take, forecast nuance, or story.\n\n"
            "Full links → https://linktr.ee/URP\n",
            encoding="utf-8",
        )
    meta = template / "meta.yaml"
    if not meta.exists():
        meta.write_text(
            "title_hint: \"Your title hint\"\n"
            "platforms: [x, instagram, tiktok, youtube]\n"
            "content_type: bundle\n"
            "tags: [WNY, Buffalo]\n"
            "cta: \"https://linktr.ee/URP\"\n"
            "notes: \"\"\n",
            encoding="utf-8",
        )
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(
            "DOC WEATHER CONTENT LIBRARY\n"
            "===========================\n\n"
            "videos/ready/   → finished clips\n"
            "articles/ready/ → finished writing (.md / .txt)\n"
            "bundles/        → folder per story: video + insight.md + meta.yaml\n\n"
            "Copy bundles/_TEMPLATE to bundles/YYYY-MM-DD-slug and fill it in.\n"
            "See social-media-liaison/docs/CONTENT_LIBRARY.md for full guide.\n",
            encoding="utf-8",
        )
    return root


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _title_from_article(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or fallback
        if s:
            return s[:120]
    return fallback


def _load_meta(folder: Path) -> dict[str, Any]:
    for name in ("meta.yaml", "meta.yml", "meta.json"):
        p = folder / name
        if not p.exists():
            continue
        try:
            if p.suffix == ".json":
                import json

                return json.loads(p.read_text(encoding="utf-8")) or {}
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.warning("Bad meta in %s: %s", p, e)
    return {}


def scan_library(root: Path | None = None) -> list[ContentItem]:
    root = ensure_library(root)
    items: list[ContentItem] = []

    for stage in ("inbox", "ready", "posted"):
        vdir = root / "videos" / stage
        if vdir.exists():
            for f in sorted(vdir.iterdir()):
                if f.is_file() and f.suffix.lower() in VIDEO_EXTS and not f.name.startswith("."):
                    items.append(
                        ContentItem(
                            kind="video",
                            path=str(f),
                            title_hint=f.stem.replace("-", " ").replace("_", " "),
                            video_path=str(f),
                            status_folder=stage,
                        )
                    )
        adir = root / "articles" / stage
        if adir.exists():
            for f in sorted(adir.iterdir()):
                if f.is_file() and f.suffix.lower() in ARTICLE_EXTS and not f.name.startswith("."):
                    body = _read_text(f)
                    items.append(
                        ContentItem(
                            kind="article",
                            path=str(f),
                            title_hint=_title_from_article(body, f.stem.replace("-", " ")),
                            body=body,
                            article_path=str(f),
                            status_folder=stage,
                        )
                    )

    broot = root / "bundles"
    if broot.exists():
        for folder in sorted(broot.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
                continue
            meta = _load_meta(folder)
            video = ""
            article = ""
            for f in folder.iterdir():
                if f.name.startswith("."):
                    continue
                if f.suffix.lower() in VIDEO_EXTS and not video:
                    video = str(f)
                if f.suffix.lower() in ARTICLE_EXTS and f.stem.lower() in {
                    "insight",
                    "article",
                    "caption",
                    "post",
                    "writeup",
                }:
                    article = str(f)
                elif f.suffix.lower() in ARTICLE_EXTS and not article:
                    article = str(f)
            if not video and not article:
                continue
            body = _read_text(Path(article)) if article else ""
            title = (
                str(meta.get("title_hint") or meta.get("title") or "").strip()
                or _title_from_article(body, folder.name.replace("-", " "))
            )
            platforms = meta.get("platforms") or []
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",") if p.strip()]
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            kind = "bundle" if video and article else ("video" if video else "article")
            # staged: if inside posted marker file
            stage = "ready"
            if (folder / ".posted").exists():
                stage = "posted"
            elif (folder / ".inbox").exists():
                stage = "inbox"
            items.append(
                ContentItem(
                    kind=kind if kind != "bundle" else "bundle",
                    path=str(folder),
                    title_hint=title,
                    body=body,
                    video_path=video,
                    article_path=article,
                    platforms=list(platforms),
                    tags=list(tags),
                    status_folder=stage,
                    meta=meta if isinstance(meta, dict) else {},
                )
            )
    return items


def scan_ready(root: Path | None = None) -> list[ContentItem]:
    return [i for i in scan_library(root) if i.status_folder == "ready"]


def archive_item(item: ContentItem, root: Path | None = None) -> None:
    """Move video/article into posted/; mark bundle with .posted."""
    root = root or default_library_root()
    try:
        if item.kind == "bundle" or Path(item.path).is_dir():
            marker = Path(item.path) / ".posted"
            marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            return
        src = Path(item.path)
        if not src.exists():
            return
        if item.kind == "video":
            dest_dir = root / "videos" / "posted"
        else:
            dest_dir = root / "articles" / "posted"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
    except Exception as e:
        log.warning("archive failed for %s: %s", item.path, e)
