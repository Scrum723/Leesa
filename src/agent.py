"""Main agent loop: watcher + scheduler + engagement + analytics + alerts."""

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import db
from .analytics.reports import AnalyticsModule
from .config import ROOT, Settings
from .engagement.alerts import AlertService
from .engagement.monitor import EngagementMonitor
from .logging_setup import EventLog, setup_logging
from .polls.service import PollService
from .posting.orchestrator import PostingOrchestrator
from .video_watcher import VideoWatcher

log = logging.getLogger("liaison.agent")


class SocialMediaLiaisonAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        jsonl = settings.config.get("logging", {}).get("jsonl", "logs/events.jsonl")
        self.events = EventLog(ROOT / jsonl)
        self.orch = PostingOrchestrator(settings, self.events)
        self.watcher = VideoWatcher(settings, self.events)
        self.engagement = EngagementMonitor(settings, self.orch, self.events)
        self.analytics = AnalyticsModule(settings, self.orch, self.events)
        self.polls = PollService(settings, self.orch, self.events)
        self.alerts = AlertService(settings, self.events)
        self.scheduler = BackgroundScheduler()
        self._stop = threading.Event()

    def start(self, run_dashboard: bool = True) -> None:
        setup_logging(self.settings.config.get("logging"))
        db.init_db()
        self._seed_accounts()

        log.info(
            "Starting Social Media Liaison | dry_run=%s platforms=%s inbox=%s",
            self.settings.dry_run,
            self.orch.active_platforms(),
            self.settings.video_inbox,
        )
        self.events.write(
            "agent_start",
            dry_run=self.settings.dry_run,
            platforms=self.orch.active_platforms(),
        )

        self.watcher.start()
        self._configure_scheduler()
        self.scheduler.start()

        if run_dashboard:
            t = threading.Thread(target=self._run_dashboard, name="dashboard", daemon=True)
            t.start()

        def _sig(_s: int, _f: Any) -> None:
            log.info("Shutdown signal received")
            self.stop()

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)

        while not self._stop.is_set():
            time.sleep(0.5)

    def stop(self) -> None:
        self._stop.set()
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
        self.watcher.stop()
        self.events.write("agent_stop")
        log.info("Agent stopped")

    def _configure_scheduler(self) -> None:
        sched = self.settings.config.get("schedule") or {}
        tz_name = sched.get("timezone", "America/New_York")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        post_time = str(sched.get("daily_post_time", "10:00"))
        analytics_time = str(sched.get("daily_analytics_time", "21:00"))
        poll_time = str(sched.get("daily_poll_time", "09:00"))
        post_h, post_m = _parse_hhmm(post_time)
        an_h, an_m = _parse_hhmm(analytics_time)
        poll_h, poll_m = _parse_hhmm(poll_time)

        eng_every = int(sched.get("engagement_poll_seconds", 90))
        mon_every = int(sched.get("monitor_poll_seconds", 120))
        poll_check = int(sched.get("poll_results_check_seconds", 900))
        polls_enabled = bool((self.settings.config.get("polls") or {}).get("enabled", True))

        self.scheduler.add_job(
            self.job_daily_post,
            CronTrigger(hour=post_h, minute=post_m, timezone=tz),
            id="daily_post",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.job_daily_analytics,
            CronTrigger(hour=an_h, minute=an_m, timezone=tz),
            id="daily_analytics",
            replace_existing=True,
        )
        if polls_enabled:
            self.scheduler.add_job(
                self.job_daily_poll,
                CronTrigger(hour=poll_h, minute=poll_m, timezone=tz),
                id="daily_poll",
                replace_existing=True,
            )
            self.scheduler.add_job(
                self.job_poll_results,
                IntervalTrigger(seconds=max(60, poll_check)),
                id="poll_results",
                replace_existing=True,
            )
        if self.settings.auto_engage_enabled:
            self.scheduler.add_job(
                self.job_engagement,
                IntervalTrigger(seconds=max(30, eng_every)),
                id="engagement",
                replace_existing=True,
            )
        if self.settings.continuous_monitor_enabled:
            self.scheduler.add_job(
                self.job_monitor,
                IntervalTrigger(seconds=max(30, mon_every)),
                id="monitor",
                replace_existing=True,
            )
        self.scheduler.add_job(
            self.job_alerts,
            IntervalTrigger(seconds=45),
            id="alerts",
            replace_existing=True,
        )
        log.info(
            "Scheduler: poll %02d:%02d | daily post %02d:%02d %s | analytics %02d:%02d | eng every %ss",
            poll_h,
            poll_m,
            post_h,
            post_m,
            tz_name,
            an_h,
            an_m,
            eng_every,
        )

    def job_daily_poll(self) -> None:
        """09:00 Eastern daily audience poll (X native poll)."""
        log.info("Daily poll job fired")
        try:
            result = self.polls.prepare_and_post()
            if result.get("skipped"):
                log.info("Daily poll skipped: %s", result.get("reason"))
                return
            ok = bool(result.get("ok"))
            self.alerts.notify_now(
                "Daily poll posted" if ok else "Daily poll failed",
                result.get("url") or result.get("error") or "",
                severity="info" if ok else "error",
                category="poll",
                platform="x",
            )
            # Honest multi-platform status for ops reports
            for p in ("instagram", "tiktok", "youtube"):
                if not self.settings.is_platform_enabled(p):
                    continue
                # Native polls not implemented on these platforms yet
                db.create_alert(
                    "info",
                    "poll",
                    f"Poll skipped on {p}",
                    "No native poll API in LEESA yet; X poll is primary.",
                    platform=p,
                )
        except Exception as e:
            log.exception("Daily poll failed")
            db.create_alert("error", "error", "Daily poll crashed", str(e))

    def job_poll_results(self) -> None:
        """Collect results for polls whose 24h window ended."""
        try:
            collected = self.polls.collect_due_results()
            for item in collected:
                if item.get("ok"):
                    self.alerts.notify_now(
                        "Poll results ready",
                        item.get("report") or f"poll_id={item.get('poll_id')}",
                        severity="info",
                        category="poll",
                        platform="x",
                    )
        except Exception as e:
            log.exception("Poll results collection failed: %s", e)

    def job_daily_post(self) -> None:
        log.info("Daily post job fired")
        try:
            result = self.orch.process_next_queued()
            if result is None:
                log.info("No queued videos for daily post")
                self.alerts.notify_now(
                    "Daily post: queue empty",
                    "Drop a video in the inbox folder to schedule tomorrow.",
                    severity="info",
                    category="schedule",
                )
            elif result.get("deferred"):
                log.info("Daily post deferred: %s", result.get("error"))
            else:
                self.alerts.notify_now(
                    "Daily post complete",
                    f"status={result.get('status')} results={len(result.get('results') or [])}",
                    severity="info" if result.get("ok") else "error",
                    category="post",
                )
        except Exception as e:
            log.exception("Daily post failed")
            db.create_alert("error", "error", "Daily post crashed", str(e))

    def job_daily_analytics(self) -> None:
        log.info("Daily analytics job fired")
        try:
            self.analytics.collect_all()
            report = self.analytics.generate_daily_report()
            self.alerts.notify_now(
                "Daily analytics ready",
                report.get("report_path", ""),
                severity="info",
                category="analytics",
            )
        except Exception as e:
            log.exception("Analytics failed")
            db.create_alert("error", "error", "Analytics failed", str(e))

    def job_engagement(self) -> None:
        try:
            stats = self.engagement.run_once()
            log.debug("Engagement tick: %s", stats)
        except Exception as e:
            log.exception("Engagement error: %s", e)

    def job_monitor(self) -> None:
        try:
            n = self.engagement.check_high_engagement()
            if n:
                log.info("High-engagement alerts raised: %s", n)
        except Exception as e:
            log.exception("Monitor error: %s", e)

    def job_alerts(self) -> None:
        try:
            self.alerts.push_unacknowledged()
        except Exception as e:
            log.debug("Alert push: %s", e)

    def post_now(self, job_id: int | None = None) -> dict[str, Any]:
        if job_id:
            job = db.get_job(job_id)
            if not job:
                return {"ok": False, "error": "job not found"}
            return self.orch.process_job(job, force=True)
        result = self.orch.process_next_queued(force=True)
        return result or {"ok": False, "error": "queue empty"}

    def _seed_accounts(self) -> None:
        brand = self.settings.brand
        socials = brand.get("socials") or {
            "x": "charlesclottin",
            "instagram": "charlesclottin",
            "youtube": "theweathermandj",
            "tiktok": "docweather",
        }
        # Prefer config brand.socials URLs if present
        cfg_socials = brand.get("socials") or {}
        for platform in ("x", "instagram", "youtube", "tiktok"):
            if platform in cfg_socials:
                socials[platform] = cfg_socials[platform]

        status = self.settings.credentials_status()
        for platform, meta in status.items():
            handle = socials.get(platform, platform)
            if isinstance(handle, str) and handle.startswith("http"):
                handle = handle.rstrip("/").split("/")[-1]
            db.upsert_account(
                platform=platform,
                handle=str(handle).lstrip("@"),
                display_name=self.settings.streamer_name,
                enabled=self.settings.is_platform_enabled(platform),
                settings={"connected": meta["connected"], "label": meta["label"]},
            )
            if not db.get_platform_settings(platform):
                db.set_platform_settings(platform, dict(self.settings.platform_cfg(platform)))

    def _run_dashboard(self) -> None:
        from dashboard.app import create_app

        app = create_app(self)
        log.info(
            "Dashboard http://%s:%s",
            self.settings.dashboard_host,
            self.settings.dashboard_port,
        )
        app.run(
            host=self.settings.dashboard_host,
            port=self.settings.dashboard_port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        parts = value.strip().split(":")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return 10, 0
