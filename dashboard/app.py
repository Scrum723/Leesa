"""Simplistic Flask dashboard for accounts, settings, posts, analytics."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from src import db
from src.config import ROOT

if TYPE_CHECKING:
    from src.agent import SocialMediaLiaisonAgent

log = logging.getLogger("liaison.dashboard")

PLATFORMS = ["x", "instagram", "tiktok", "youtube"]


def create_app(agent: SocialMediaLiaisonAgent | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    secret = "change-me"
    if agent:
        secret = agent.settings.dashboard_secret
    app.secret_key = secret
    app.config["AGENT"] = agent

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        settings = agent.settings if agent else None
        return {
            "brand_name": (settings.streamer_name if settings else "Doc Weather"),
            "dry_run": bool(settings.dry_run) if settings else True,
            "linktree": settings.linktree if settings else "https://linktr.ee/URP",
        }

    @app.get("/")
    def index():
        jobs = db.list_jobs(limit=20)
        posts = db.list_posts(limit=20)
        alerts = db.list_alerts(limit=10)
        accounts = db.list_accounts()
        analytics = agent.analytics.summary_for_dashboard() if agent else {}
        creds = agent.settings.credentials_status() if agent else {}
        return render_template(
            "index.html",
            jobs=jobs,
            posts=posts,
            alerts=alerts,
            accounts=accounts,
            analytics=analytics,
            creds=creds,
            queue_len=len([j for j in jobs if j["status"] == "queued"]),
        )

    @app.get("/accounts")
    def accounts_page():
        accounts = db.list_accounts()
        creds = agent.settings.credentials_status() if agent else {}
        return render_template("accounts.html", accounts=accounts, creds=creds, platforms=PLATFORMS)

    @app.post("/accounts/add")
    def accounts_add():
        platform = (request.form.get("platform") or "").strip().lower()
        handle = (request.form.get("handle") or "").strip().lstrip("@")
        display = (request.form.get("display_name") or "").strip()
        enabled = request.form.get("enabled") == "on"
        if platform not in PLATFORMS or not handle:
            flash("Platform and handle are required.", "error")
            return redirect(url_for("accounts_page"))
        db.upsert_account(platform, handle, display_name=display or handle, enabled=enabled)
        flash(f"Account @{handle} on {platform} saved.", "ok")
        return redirect(url_for("accounts_page"))

    @app.post("/accounts/<int:account_id>/delete")
    def accounts_delete(account_id: int):
        db.delete_account(account_id)
        flash("Account removed.", "ok")
        return redirect(url_for("accounts_page"))

    @app.post("/accounts/<int:account_id>/toggle")
    def accounts_toggle(account_id: int):
        accounts = {a["id"]: a for a in db.list_accounts()}
        a = accounts.get(account_id)
        if not a:
            flash("Account not found.", "error")
            return redirect(url_for("accounts_page"))
        new_enabled = not bool(a["enabled"])
        db.upsert_account(
            a["platform"],
            a["handle"],
            display_name=a.get("display_name") or "",
            external_id=a.get("external_id") or "",
            enabled=new_enabled,
            settings=json.loads(a.get("settings_json") or "{}"),
        )
        flash(f"@{a['handle']} {'enabled' if new_enabled else 'disabled'}.", "ok")
        return redirect(url_for("accounts_page"))

    @app.get("/settings")
    def settings_page():
        yaml_platforms = (agent.settings.config.get("platforms") if agent else {}) or {}
        overlays = db.get_all_platform_settings()
        merged = {}
        for p in PLATFORMS:
            merged[p] = {**(yaml_platforms.get(p) or {}), **(overlays.get(p) or {})}
        schedule = (agent.settings.config.get("schedule") if agent else {}) or {}
        return render_template(
            "settings.html",
            platform_settings=merged,
            platforms=PLATFORMS,
            schedule=schedule,
            dry_run=agent.settings.dry_run if agent else True,
        )

    @app.post("/settings/<platform>")
    def settings_save(platform: str):
        platform = platform.lower()
        if platform not in PLATFORMS:
            flash("Unknown platform.", "error")
            return redirect(url_for("settings_page"))
        current = db.get_platform_settings(platform) or dict(
            (agent.settings.platform_cfg(platform) if agent else {}) or {}
        )
        current["enabled"] = request.form.get("enabled") == "on"
        current["reply_to_comments"] = request.form.get("reply_to_comments") == "on"
        current["notify_followers"] = request.form.get("notify_followers") == "on"
        current["reply_mode"] = request.form.get("reply_mode") or "ai"
        try:
            current["max_hashtags"] = int(request.form.get("max_hashtags") or current.get("max_hashtags") or 8)
        except ValueError:
            pass
        try:
            current["max_replies_per_hour"] = int(
                request.form.get("max_replies_per_hour") or current.get("max_replies_per_hour") or 15
            )
        except ValueError:
            pass
        kw = request.form.get("engage_keywords") or ""
        current["engage_keywords"] = [k.strip() for k in kw.split(",") if k.strip()]
        if platform == "youtube":
            current["privacy_status"] = request.form.get("privacy_status") or "public"
            current["notify_subscribers"] = request.form.get("notify_subscribers") == "on"
        if platform == "tiktok":
            current["privacy_level"] = request.form.get("privacy_level") or "PUBLIC_TO_EVERYONE"
        db.set_platform_settings(platform, current)
        flash(f"{platform} settings saved.", "ok")
        return redirect(url_for("settings_page"))

    @app.get("/posts")
    def posts_page():
        posts = db.list_posts(limit=100)
        jobs = db.list_jobs(limit=50)
        return render_template("posts.html", posts=posts, jobs=jobs)

    @app.post("/posts/run-next")
    def posts_run_next():
        if not agent:
            flash("Agent not attached.", "error")
            return redirect(url_for("posts_page"))
        result = agent.post_now()
        if result.get("ok"):
            flash(f"Posted: {result.get('status')}", "ok")
        else:
            flash(f"Post failed: {result.get('error') or result}", "error")
        return redirect(url_for("posts_page"))

    @app.post("/posts/job/<int:job_id>/run")
    def posts_run_job(job_id: int):
        if not agent:
            flash("Agent not attached.", "error")
            return redirect(url_for("posts_page"))
        result = agent.post_now(job_id=job_id)
        flash(f"Job {job_id}: {result.get('status') or result.get('error')}", "ok" if result.get("ok") else "error")
        return redirect(url_for("posts_page"))

    @app.get("/analytics")
    def analytics_page():
        summary = agent.analytics.summary_for_dashboard() if agent else {}
        reports = sorted((ROOT / "data" / "charts").glob("report_*.md"), reverse=True) if (ROOT / "data" / "charts").exists() else []
        report_previews = []
        for r in reports[:5]:
            report_previews.append({"name": r.name, "path": str(r), "text": r.read_text(encoding="utf-8")[:2000]})
        return render_template("analytics.html", summary=summary, reports=report_previews)

    @app.post("/analytics/refresh")
    def analytics_refresh():
        if not agent:
            flash("Agent not attached.", "error")
            return redirect(url_for("analytics_page"))
        agent.analytics.collect_all()
        agent.analytics.generate_daily_report()
        flash("Analytics refreshed.", "ok")
        return redirect(url_for("analytics_page"))

    @app.get("/charts/<path:filename>")
    def charts(filename: str):
        return send_from_directory(str(ROOT / "data" / "charts"), filename)

    @app.get("/alerts")
    def alerts_page():
        alerts = db.list_alerts(limit=100)
        return render_template("alerts.html", alerts=alerts)

    @app.post("/alerts/<int:alert_id>/ack")
    def alerts_ack(alert_id: int):
        db.ack_alert(alert_id)
        flash("Alert acknowledged.", "ok")
        return redirect(request.referrer or url_for("alerts_page"))

    @app.get("/library")
    def library_page():
        from src.content_library import default_library_root, ensure_library, scan_library

        root = (
            agent.settings.content_library
            if agent and getattr(agent.settings, "content_library", None)
            else default_library_root()
        )
        ensure_library(root)
        items = [i.to_dict() for i in scan_library(root)]
        # persist snapshot
        for it in items:
            db.upsert_content_item({**it, "job_status": "discovered"})
        return render_template(
            "library.html",
            items=items,
            library_root=str(root),
            counts={
                "video": sum(1 for i in items if i["kind"] == "video"),
                "article": sum(1 for i in items if i["kind"] == "article"),
                "bundle": sum(1 for i in items if i["kind"] == "bundle"),
                "ready": sum(1 for i in items if i["status_folder"] == "ready"),
            },
        )

    @app.post("/library/scan")
    def library_scan():
        return redirect(url_for("library_page"))

    @app.post("/library/post")
    def library_post():
        if not agent:
            flash("Agent not attached.", "error")
            return redirect(url_for("library_page"))
        path = (request.form.get("path") or "").strip()
        from src.content_library import scan_library

        root = agent.settings.content_library
        match = next((i for i in scan_library(root) if i.path == path), None)
        if not match:
            flash("Item not found in library.", "error")
            return redirect(url_for("library_page"))
        result = agent.orch.process_content_item(match.to_dict(), force=True)
        flash(
            f"Posted {match.kind}: {'ok' if result.get('ok') else result.get('error')}",
            "ok" if result.get("ok") else "error",
        )
        return redirect(url_for("library_page"))

    # --- TikTok Developer Portal website verification ---
    @app.get("/tiktokIcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8.txt")
    def tiktok_site_verification():
        """Serve TikTok domain verification file at site root (required by TikTok portal)."""
        static_dir = Path(__file__).parent / "static"
        return send_from_directory(
            str(static_dir),
            "tiktokIcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8.txt",
            mimetype="text/plain",
        )

    # --- Legal / policy pages (public links for app review & users) ---
    @app.get("/legal")
    def legal_hub():
        return render_template("legal_hub.html")

    @app.get("/legal/terms")
    def legal_terms():
        return render_template("legal_terms.html")

    @app.get("/legal/privacy")
    def legal_privacy():
        return render_template("legal_privacy.html")

    @app.get("/legal/data-collection")
    def legal_data():
        return render_template("legal_data.html")

    @app.get("/legal/violations")
    def legal_violations():
        return render_template("legal_violations.html")

    # Convenience aliases
    @app.get("/terms")
    def terms_alias():
        return redirect(url_for("legal_terms"))

    @app.get("/privacy")
    def privacy_alias():
        return redirect(url_for("legal_privacy"))

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "dry_run": agent.settings.dry_run if agent else True,
                "platforms": agent.orch.active_platforms() if agent else [],
                "jobs_queued": len(db.list_jobs(status="queued", limit=100)),
                "alerts_open": len(db.list_alerts(unacked_only=True, limit=100)),
                "credentials": agent.settings.credentials_status() if agent else {},
                "dashboard_url": "https://social-media-liaison-production.up.railway.app",
            }
        )

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(db.list_jobs(limit=50))

    @app.get("/api/library")
    def api_library():
        from src.content_library import default_library_root, ensure_library, scan_library

        root = (
            agent.settings.content_library
            if agent and getattr(agent.settings, "content_library", None)
            else default_library_root()
        )
        ensure_library(root)
        items = [i.to_dict() for i in scan_library(root)]
        return jsonify({"root": str(root), "items": items, "count": len(items)})

    @app.get("/api/analytics")
    def api_analytics():
        if not agent:
            return jsonify({})
        return jsonify(agent.analytics.summary_for_dashboard())

    return app
