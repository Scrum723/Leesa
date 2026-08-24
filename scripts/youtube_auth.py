#!/usr/bin/env python3
"""One-time YouTube OAuth — opens browser, saves data/youtube_token.json.

IMPORTANT (Google Testing mode):
  1. OAuth consent screen must be "Testing"
  2. Your Google account (channel owner) must be listed under Test users
  3. We only request youtube.upload (upload Shorts) — NOT force-ssl/delete
     so Google is less likely to block unverified apps.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_settings

# Upload-only — enough for LEESA Shorts posting. Avoids "permanently delete" scare.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
]


def main() -> None:
    settings = load_settings()
    secrets = Path(settings.youtube_client_secrets_file).expanduser()
    token_path = Path(settings.youtube_token_file).expanduser()
    if not secrets.exists():
        print(f"Missing client secrets: {secrets}")
        print("Set YOUTUBE_CLIENT_SECRETS_FILE or recreate data/youtube_client_secrets.json")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    print("=" * 60)
    print("LEESA YouTube OAuth")
    print("=" * 60)
    print("Before continuing, in Google Cloud Console:")
    print("  APIs & Services → OAuth consent screen")
    print("  • Publishing status: Testing")
    print("  • Test users: ADD the SAME Google account you will sign in with")
    print("    (the WeatherWorldCC / channel owner Gmail)")
    print("  • Scopes: include .../auth/youtube.upload")
    print("  • Enable API: YouTube Data API v3")
    print()
    print("Scopes requested (upload only):")
    for s in SCOPES:
        print(f"  - {s}")
    print()
    print("Opening browser — sign in as the TEST USER / channel owner…")
    print("=" * 60)

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    # port=0 picks a free local port; Google Desktop clients allow http://localhost
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except OSError:
        pass

    print()
    print(f"Saved token → {token_path}")
    print("YouTube upload auth is ready for LEESA.")
    print("Keep DRY_RUN=true until you want a live Short.")
    print()
    print("If you still see access_denied / 403:")
    print("  1) The Google account is NOT on the Test users list — add it and retry")
    print("  2) You signed into a different Google account than the test user")
    print("  3) YouTube Data API v3 is not enabled on this Cloud project")


if __name__ == "__main__":
    main()
