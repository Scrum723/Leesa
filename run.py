#!/usr/bin/env python3
"""Launch the Doc Weather Social Media Liaison agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import SocialMediaLiaisonAgent
from src.config import load_settings
from src import db
from src.logging_setup import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Social Media Liaison — watch inbox, post to X/IG/TikTok/YouTube, engage, analytics"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log actions without calling platform APIs")
    parser.add_argument("--live", action="store_true", help="Force live mode (override DRY_RUN)")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument(
        "--platforms",
        type=str,
        default=None,
        help="Comma list: x,instagram,tiktok,youtube",
    )
    parser.add_argument("--no-dashboard", action="store_true", help="Run agent without web UI")
    parser.add_argument("--dashboard-only", action="store_true", help="Only start the web dashboard")
    parser.add_argument("--post-now", action="store_true", help="Process next queued video then exit")
    parser.add_argument("--scan", action="store_true", help="Scan inbox, enqueue new videos, exit")
    parser.add_argument("--analytics-now", action="store_true", help="Collect metrics + write report, exit")
    parser.add_argument("--poll-now", action="store_true", help="Generate + post today's audience poll (X), exit")
    parser.add_argument("--poll-results-now", action="store_true", help="Collect due poll results, exit")
    parser.add_argument("--inbox", type=Path, default=None, help="Override video inbox folder")
    args = parser.parse_args()

    settings = load_settings(config_path=args.config)
    if args.dry_run:
        settings.dry_run = True
    if args.live:
        settings.dry_run = False
    if args.platforms:
        settings.enabled_platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    if args.inbox:
        settings.video_inbox = args.inbox.expanduser()

    setup_logging(settings.config.get("logging"))
    db.init_db()

    agent = SocialMediaLiaisonAgent(settings)

    if args.scan:
        n = agent.watcher.scan_existing()
        print(f"Enqueued {n} new video(s) from {settings.video_inbox}")
        return

    if args.post_now:
        agent.watcher.scan_existing()
        result = agent.post_now()
        print(result)
        return

    if args.analytics_now:
        agent.analytics.collect_all()
        report = agent.analytics.generate_daily_report()
        print(report)
        return

    if args.poll_now:
        result = agent.polls.prepare_and_post(force=True)
        print(result)
        return

    if args.poll_results_now:
        print(agent.polls.collect_due_results())
        return

    if args.dashboard_only:
        from dashboard.app import create_app

        app = create_app(agent)
        print(f"Dashboard http://{settings.dashboard_host}:{settings.dashboard_port}")
        app.run(
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
        return

    print(
        f"Starting liaison dry_run={settings.dry_run} "
        f"platforms={settings.enabled_platforms} "
        f"inbox={settings.video_inbox} "
        f"dashboard=http://{settings.dashboard_host}:{settings.dashboard_port}"
    )
    agent.start(run_dashboard=not args.no_dashboard)


if __name__ == "__main__":
    main()
