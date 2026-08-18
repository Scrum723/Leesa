"""Load env + YAML config for the social media liaison agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or not str(val).strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


@dataclass
class Settings:
    dry_run: bool = True
    xai_api_key: str = ""
    xai_model: str = "grok-4.5"
    video_inbox: Path = field(default_factory=lambda: ROOT / "inbox")
    video_inbox_extra: Path | None = None
    content_library: Path = field(
        default_factory=lambda: Path.home() / "Desktop" / "Doc Weather Content"
    )
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787
    dashboard_secret: str = "change-me"
    # X
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""
    x_bearer_token: str = ""
    x_oauth2_client_id: str = ""
    x_oauth2_client_secret: str = ""
    x_oauth2_access_token: str = ""
    x_oauth2_refresh_token: str = ""
    # Instagram / Meta
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    facebook_page_id: str = ""
    # TikTok
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""
    tiktok_open_id: str = ""
    # YouTube
    youtube_client_secrets_file: str = ""
    youtube_token_file: str = ""
    youtube_channel_id: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    # Alerts
    alert_webhook_url: str = ""
    alert_email: str = ""
    # Toggles
    ai_content_enabled: bool = True
    auto_engage_enabled: bool = True
    analytics_enabled: bool = True
    continuous_monitor_enabled: bool = True
    enabled_platforms: list[str] = field(default_factory=lambda: ["x", "instagram", "tiktok", "youtube"])
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def brand(self) -> dict[str, Any]:
        return self.config.get("brand", {})

    @property
    def linktree(self) -> str:
        return self.brand.get("linktree", "https://linktr.ee/URP")

    @property
    def streamer_name(self) -> str:
        return self.brand.get("streamer_name", "Doc Weather")

    def platform_cfg(self, name: str) -> dict[str, Any]:
        return (self.config.get("platforms") or {}).get(name, {})

    def is_platform_enabled(self, name: str) -> bool:
        if name not in self.enabled_platforms:
            return False
        cfg = self.platform_cfg(name)
        return bool(cfg.get("enabled", True))

    def credentials_status(self) -> dict[str, dict[str, Any]]:
        """Whether each platform has enough credentials for real posting."""
        return {
            "x": {
                "connected": bool(
                    (self.x_api_key and self.x_api_secret and self.x_access_token and self.x_access_token_secret)
                    or bool(self.x_oauth2_access_token)
                ),
                "label": "X (Twitter)",
            },
            "instagram": {
                "connected": bool(self.instagram_access_token and self.instagram_business_account_id),
                "label": "Instagram",
            },
            "tiktok": {
                "connected": bool(self.tiktok_access_token),
                "label": "TikTok",
            },
            "youtube": {
                "connected": bool(
                    (self.youtube_client_secrets_file and Path(self.youtube_client_secrets_file).expanduser().exists())
                    or (self.youtube_client_id and self.youtube_refresh_token)
                    or (self.youtube_token_file and Path(self.youtube_token_file).expanduser().exists())
                ),
                "label": "YouTube",
            },
        }


def load_settings(config_path: Path | None = None) -> Settings:
    load_dotenv(ROOT / ".env")
    path = config_path or (ROOT / "config.yaml")
    cfg = load_yaml(path)

    inbox = os.getenv("VIDEO_INBOX") or str(ROOT / "inbox")
    extra = os.getenv("VIDEO_INBOX_EXTRA") or None
    # Prefer dedicated library; fall back to videos/ready under library
    lib = os.getenv("CONTENT_LIBRARY") or str(Path.home() / "Desktop" / "Doc Weather Content")

    enabled = cfg.get("enabled_platforms") or ["x", "instagram", "tiktok", "youtube"]
    env_platforms = os.getenv("PLATFORMS")
    if env_platforms:
        enabled = [p.strip().lower() for p in env_platforms.split(",") if p.strip()]

    yt_token = os.getenv("YOUTUBE_TOKEN_FILE") or str(DATA / "youtube_token.json")

    return Settings(
        dry_run=_env_bool("DRY_RUN", True),
        xai_api_key=os.getenv("XAI_API_KEY", ""),
        xai_model=os.getenv("XAI_MODEL", "grok-4.5"),
        video_inbox=Path(inbox).expanduser(),
        video_inbox_extra=Path(extra).expanduser() if extra else None,
        content_library=Path(lib).expanduser(),
        dashboard_host=os.getenv("DASHBOARD_HOST", "0.0.0.0" if os.getenv("PORT") or os.getenv("RAILWAY_ENVIRONMENT") else "127.0.0.1"),
        dashboard_port=_env_int("PORT", _env_int("DASHBOARD_PORT", 8787)),
        dashboard_secret=os.getenv("DASHBOARD_SECRET", "change-me"),
        x_api_key=os.getenv("X_API_KEY", ""),
        x_api_secret=os.getenv("X_API_SECRET", ""),
        x_access_token=os.getenv("X_ACCESS_TOKEN", ""),
        x_access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET", ""),
        x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
        x_oauth2_client_id=os.getenv("X_OAUTH2_CLIENT_ID") or os.getenv("X_CLIENT_ID", ""),
        x_oauth2_client_secret=os.getenv("X_OAUTH2_CLIENT_SECRET") or os.getenv("X_CLIENT_SECRET", ""),
        x_oauth2_access_token=os.getenv("X_OAUTH2_ACCESS_TOKEN", ""),
        x_oauth2_refresh_token=os.getenv("X_OAUTH2_REFRESH_TOKEN", ""),
        instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        instagram_business_account_id=os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
        facebook_page_id=os.getenv("FACEBOOK_PAGE_ID", ""),
        tiktok_client_key=os.getenv("TIKTOK_CLIENT_KEY", ""),
        tiktok_client_secret=os.getenv("TIKTOK_CLIENT_SECRET", ""),
        tiktok_access_token=os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        tiktok_refresh_token=os.getenv("TIKTOK_REFRESH_TOKEN", ""),
        tiktok_open_id=os.getenv("TIKTOK_OPEN_ID", ""),
        youtube_client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", ""),
        youtube_token_file=yt_token,
        youtube_channel_id=os.getenv("YOUTUBE_CHANNEL_ID", ""),
        youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
        youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        youtube_refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
        alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL", ""),
        alert_email=os.getenv("ALERT_EMAIL", ""),
        ai_content_enabled=_env_bool("AI_CONTENT_ENABLED", True),
        auto_engage_enabled=_env_bool("AUTO_ENGAGE_ENABLED", True),
        analytics_enabled=_env_bool("ANALYTICS_ENABLED", True),
        continuous_monitor_enabled=_env_bool("CONTINUOUS_MONITOR_ENABLED", True),
        enabled_platforms=list(enabled),
        config=cfg,
    )
