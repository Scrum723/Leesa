"""Lightweight smoke tests for LEESA (Doc Weather Social Media Liaison)."""

from __future__ import annotations

import os

os.environ.setdefault("DRY_RUN", "true")


def test_settings_load():
    from src.config import load_settings

    s = load_settings()
    assert s.streamer_name
    assert isinstance(s.enabled_platforms, list)


def test_db_init(tmp_path, monkeypatch):
    from src import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    assert (tmp_path / "test.db").exists()


def test_legal_routes():
    from src import db
    from src.agent import SocialMediaLiaisonAgent
    from src.config import load_settings
    from dashboard.app import create_app

    s = load_settings()
    db.init_db()
    app = create_app(SocialMediaLiaisonAgent(s))
    client = app.test_client()
    for path in (
        "/legal",
        "/legal/terms",
        "/legal/privacy",
        "/legal/data-collection",
        "/legal/violations",
        "/api/status",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_content_library_ensure(tmp_path):
    from src.content_library import ensure_library, scan_library

    root = ensure_library(tmp_path / "lib")
    assert (root / "videos" / "ready").is_dir()
    assert (root / "articles" / "ready").is_dir()
    assert (root / "bundles" / "_TEMPLATE").is_dir()
    items = scan_library(root)
    assert isinstance(items, list)
