#!/usr/bin/env python3
"""One-time YouTube OAuth — opens browser, saves data/youtube_token.json."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_settings


def main() -> None:
    settings = load_settings()
    secrets = Path(settings.youtube_client_secrets_file).expanduser()
    token_path = Path(settings.youtube_token_file).expanduser()
    if not secrets.exists():
        print(f"Missing client secrets: {secrets}")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
    print("Opening browser for Google sign-in (choose Doc Weather / channel owner)…")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved token → {token_path}")
    print("YouTube is ready for the liaison agent.")


if __name__ == "__main__":
    main()
