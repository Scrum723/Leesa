#!/usr/bin/env python3
"""Print credential readiness (never prints secret values)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_settings


def mask(ok: bool) -> str:
    return "READY" if ok else "MISSING"


def main() -> None:
    s = load_settings()
    print("Inbox:", s.video_inbox, "exists=", s.video_inbox.exists())
    print("DRY_RUN:", s.dry_run)
    print()
    status = s.credentials_status()
    for k, v in status.items():
        print(f"{v['label']:12} {mask(v['connected'])}")
    print()
    print("Details (presence only):")
    print("  X API key/secret:", bool(s.x_api_key and s.x_api_secret))
    print("  X user access token+secret:", bool(s.x_access_token and s.x_access_token_secret))
    print("  X bearer:", bool(s.x_bearer_token))
    print("  IG token+business id:", bool(s.instagram_access_token and s.instagram_business_account_id))
    print("  TikTok client key/secret:", bool(s.tiktok_client_key and s.tiktok_client_secret))
    print("  TikTok user access token:", bool(s.tiktok_access_token))
    print("  YouTube client secrets file:", bool(s.youtube_client_secrets_file and Path(s.youtube_client_secrets_file).exists()))
    print("  YouTube token file:", bool(s.youtube_token_file and Path(s.youtube_token_file).expanduser().exists()))
    print("  XAI key:", bool(s.xai_api_key))
    print()
    if not (s.x_access_token and s.x_access_token_secret):
        print("X: open developer.x.com → your app → Keys and tokens → generate Access Token & Secret")
    if not s.tiktok_access_token:
        print("TikTok: complete Login Kit / Content Posting OAuth to get user access token")
    if not (s.youtube_token_file and Path(s.youtube_token_file).expanduser().exists()):
        print("YouTube: run  python scripts/youtube_auth.py")
    if not s.xai_api_key:
        print("SpaceXAI: set XAI_API_KEY from console.x.ai for viral captions")


if __name__ == "__main__":
    main()
