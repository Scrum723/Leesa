"""Generate platform-optimized titles, descriptions, and hashtags via SpaceXAI."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import GeneratedContent

log = logging.getLogger("liaison.ai")


class ContentGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None
        if settings.xai_api_key and settings.ai_content_enabled:
            self._client = OpenAI(
                api_key=settings.xai_api_key,
                base_url="https://api.x.ai/v1",
            )
        else:
            log.warning("AI content generation limited — set XAI_API_KEY for full generation.")

    @property
    def available(self) -> bool:
        return self._client is not None

    def generate_for_video(
        self,
        video_path: Path,
        platforms: list[str] | None = None,
        hint: str = "",
    ) -> dict[str, GeneratedContent]:
        platforms = platforms or [
            p for p in self.settings.enabled_platforms if self.settings.is_platform_enabled(p)
        ]
        stem = video_path.stem.replace("_", " ").replace("-", " ").strip()
        hint = hint or stem

        if self.available:
            try:
                return self._generate_ai(hint, platforms, video_path.name)
            except Exception as e:
                log.exception("AI content generation failed, using fallback: %s", e)

        return {p: self._fallback(p, hint) for p in platforms}

    def reply_to_comment(
        self,
        *,
        platform: str,
        author: str,
        comment: str,
        post_title: str = "",
    ) -> str | None:
        if not self.available or not self._client:
            return self._template_reply(author, comment)

        brand = self.settings.brand
        system = (
            brand.get("persona", "You are a friendly social media manager.")
            + f"\nOfficial link hub: {self.settings.linktree}"
            + f"\nBrand: {self.settings.streamer_name}"
            + "\nReply briefly (1-2 short sentences). Warm, accurate, no spam hashtags."
            + " Never invent weather warnings. Invite them to linktree if relevant."
        )
        user = (
            f"Platform: {platform}\n"
            f"Post context: {post_title or 'weather short'}\n"
            f"@{author} commented: {comment}\n"
            "Write the reply only."
        )
        try:
            resp = self._client.chat.completions.create(
                model=self.settings.xai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
                max_tokens=120,
            )
            text = (resp.choices[0].message.content or "").strip().strip('"').strip("'")
            return text[:400] if text else None
        except Exception as e:
            log.warning("AI reply failed: %s", e)
            return self._template_reply(author, comment)

    def _generate_ai(
        self, hint: str, platforms: list[str], filename: str
    ) -> dict[str, GeneratedContent]:
        assert self._client is not None
        brand = self.settings.brand
        content_cfg = self.settings.config.get("content", {})
        default_tags = brand.get("default_hashtags") or []
        cta = content_cfg.get("cta_url") or self.settings.linktree

        system = (
            brand.get("persona", "")
            + "\nYou write viral social captions for weather short-form video."
            + " Return ONLY valid JSON. Maximize reach with strong hooks under 3 seconds of text."
            + " No medical/legal claims. Stay data-honest for weather content."
        )

        limits = {
            p: {
                "title_max": (content_cfg.get("title_max_chars") or {}).get(p, 100),
                "desc_max": (content_cfg.get("description_max_chars") or {}).get(p, 500),
                "max_hashtags": int(self.settings.platform_cfg(p).get("max_hashtags", 8)),
            }
            for p in platforms
        }

        user = f"""Create platform-specific content for this weather short video.

Filename: {filename}
Topic hint: {hint}
Brand: {self.settings.streamer_name}
CTA URL (include once where allowed): {cta}
Default hashtag pool: {default_tags}
Platform limits: {json.dumps(limits)}

Return JSON object keyed by platform name. Each value:
{{
  "title": "attention-grabbing title",
  "description": "body/caption without hashtag block",
  "hashtags": ["#Tag1", "#Tag2"],
  "notify_text": "short fan-notify message for a follow-up post or story"
}}

Platforms: {platforms}
Tips:
- X: punchy hook, few hashtags, numbers if possible
- Instagram: Reels energy, emoji sparingly, 8-12 tags
- TikTok: hook-first, trending weather tags, county/city
- YouTube: Shorts SEO title, searchable description, tags as keywords
"""

        resp = self._client.chat.completions.create(
            model=self.settings.xai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.8,
            max_tokens=2000,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = _extract_json(raw)
        out: dict[str, GeneratedContent] = {}
        for p in platforms:
            item = data.get(p) if isinstance(data, dict) else None
            if not isinstance(item, dict):
                out[p] = self._fallback(p, hint)
                continue
            tags = item.get("hashtags") or []
            if isinstance(tags, str):
                tags = [t for t in tags.split() if t]
            tags = [t if str(t).startswith("#") else f"#{t}" for t in tags]
            max_tags = int(self.settings.platform_cfg(p).get("max_hashtags", 8))
            out[p] = GeneratedContent(
                platform=p,
                title=str(item.get("title") or hint)[:200],
                description=str(item.get("description") or ""),
                hashtags=tags[:max_tags],
                notify_text=str(item.get("notify_text") or ""),
            )
        return out

    def _fallback(self, platform: str, hint: str) -> GeneratedContent:
        brand = self.settings.brand
        tags = list(brand.get("default_hashtags") or ["#Weather", "#WNYWeather"])
        max_tags = int(self.settings.platform_cfg(platform).get("max_hashtags", 8))
        tags = tags[:max_tags]
        title = f"{hint} | {self.settings.streamer_name}"
        if len(title) > 100:
            title = hint[:97] + "…"
        desc = (
            f"{hint}\n\nStay accurate. Stay informed. — {self.settings.streamer_name}\n"
            f"All links → {self.settings.linktree}"
        )
        notify = f"New video live: {hint} → {self.settings.linktree}"
        return GeneratedContent(
            platform=platform,
            title=title,
            description=desc,
            hashtags=tags,
            notify_text=notify,
        )

    def _template_reply(self, author: str, comment: str) -> str:
        low = comment.lower()
        if any(w in low for w in ("thank", "love", "great", "awesome", "helpful")):
            return f"Appreciate you @{author}! Stay accurate. Stay informed. 🗺️ {self.settings.linktree}"
        if "?" in comment:
            return (
                f"Great question @{author} — full maps + links here: {self.settings.linktree} "
                f"— {self.settings.streamer_name}"
            )
        return f"Thanks for watching @{author}! More forecasts → {self.settings.linktree}"


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group(0))
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
