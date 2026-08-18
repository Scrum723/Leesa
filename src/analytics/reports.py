"""Daily engagement charts + performance reports."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import db
from ..config import ROOT, Settings
from ..logging_setup import EventLog
from ..posting.orchestrator import PostingOrchestrator

log = logging.getLogger("liaison.analytics")


class AnalyticsModule:
    def __init__(
        self,
        settings: Settings,
        orchestrator: PostingOrchestrator | None = None,
        events: EventLog | None = None,
    ) -> None:
        self.settings = settings
        self.orch = orchestrator or PostingOrchestrator(settings)
        self.events = events or EventLog()
        cfg = settings.config.get("analytics") or {}
        self.chart_dir = ROOT / cfg.get("chart_dir", "data/charts")
        self.chart_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> int:
        if not self.settings.analytics_enabled:
            return 0
        n = 0
        for post in db.list_posts(limit=100):
            ext = post.get("external_id") or ""
            if not ext or ext.startswith("dry_"):
                continue
            client = self.orch.clients.get(post["platform"])
            if not client:
                continue
            try:
                m = client.fetch_metrics(ext)
            except Exception as e:
                log.debug("metrics %s: %s", post["platform"], e)
                continue
            db.insert_metrics(
                platform=post["platform"],
                post_external_id=ext,
                job_id=post.get("job_id"),
                views=m.get("views", 0),
                likes=m.get("likes", 0),
                comments=m.get("comments", 0),
                shares=m.get("shares", 0),
                saves=m.get("saves", 0),
            )
            n += 1
        self.events.write("metrics_collected", count=n)
        return n

    def generate_daily_report(self) -> dict[str, Any]:
        metrics = db.recent_metrics(days=7)
        posts = db.list_posts(limit=50)
        jobs = db.list_jobs(limit=30)

        by_platform: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for m in metrics:
            p = m["platform"]
            by_platform[p]["views"] += int(m.get("views") or 0)
            by_platform[p]["likes"] += int(m.get("likes") or 0)
            by_platform[p]["comments"] += int(m.get("comments") or 0)
            by_platform[p]["shares"] += int(m.get("shares") or 0)
            by_platform[p]["saves"] += int(m.get("saves") or 0)

        chart_paths = self._write_charts(metrics, by_platform)
        report_path = self.chart_dir / f"report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
        lines = [
            f"# Daily Social Performance — {datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"**Brand:** {self.settings.streamer_name}",
            f"**Posts tracked:** {len(posts)}",
            f"**Jobs:** {len(jobs)}",
            "",
            "## Totals by platform (last 7 days of samples)",
            "",
            "| Platform | Views | Likes | Comments | Shares | Saves |",
            "|----------|------:|------:|---------:|-------:|------:|",
        ]
        for p, vals in sorted(by_platform.items()):
            lines.append(
                f"| {p} | {vals['views']} | {vals['likes']} | {vals['comments']} | {vals['shares']} | {vals['saves']} |"
            )
        lines += ["", "## Charts", ""]
        for label, path in chart_paths.items():
            lines.append(f"- **{label}:** `{path}`")
        lines += ["", "## Recent posts", ""]
        for post in posts[:15]:
            lines.append(
                f"- [{post['platform']}] {post.get('title') or '(no title)'} — "
                f"{post.get('url') or post.get('external_id')} ({post.get('status')})"
            )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.events.write("daily_report", path=str(report_path), platforms=list(by_platform.keys()))
        log.info("Daily report written: %s", report_path)
        return {
            "report_path": str(report_path),
            "charts": chart_paths,
            "by_platform": {k: dict(v) for k, v in by_platform.items()},
            "posts": len(posts),
        }

    def _write_charts(
        self,
        metrics: list[dict[str, Any]],
        by_platform: dict[str, dict[str, int]],
    ) -> dict[str, str]:
        paths: dict[str, str] = {}
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as e:
            log.warning("matplotlib unavailable: %s", e)
            return paths

        # Bar chart: likes by platform
        if by_platform:
            platforms = list(by_platform.keys())
            likes = [by_platform[p]["likes"] for p in platforms]
            views = [by_platform[p]["views"] for p in platforms]
            fig, ax = plt.subplots(figsize=(8, 4.5))
            x = range(len(platforms))
            ax.bar([i - 0.2 for i in x], views, width=0.4, label="Views")
            ax.bar([i + 0.2 for i in x], likes, width=0.4, label="Likes")
            ax.set_xticks(list(x))
            ax.set_xticklabels(platforms)
            ax.set_title(f"{self.settings.streamer_name} — 7d engagement")
            ax.legend()
            ax.set_ylabel("Count")
            fig.tight_layout()
            p = self.chart_dir / "engagement_by_platform.png"
            fig.savefig(p, dpi=120)
            plt.close(fig)
            paths["engagement_by_platform"] = str(p)

        # Time series of likes if enough points
        if len(metrics) >= 2:
            fig, ax = plt.subplots(figsize=(9, 4))
            series: dict[str, list[tuple[str, int]]] = defaultdict(list)
            for m in metrics:
                series[m["platform"]].append((m["fetched_at"][:16], int(m.get("likes") or 0)))
            for platform, pts in series.items():
                ax.plot(range(len(pts)), [v for _, v in pts], marker="o", label=platform)
            ax.set_title("Likes over recent samples")
            ax.set_xlabel("Sample #")
            ax.set_ylabel("Likes")
            ax.legend()
            fig.tight_layout()
            p = self.chart_dir / "likes_timeseries.png"
            fig.savefig(p, dpi=120)
            plt.close(fig)
            paths["likes_timeseries"] = str(p)

        # Per-post latest snapshot chart
        posts = db.list_posts(limit=12)
        if posts:
            labels = []
            vals = []
            for post in reversed(posts[:10]):
                labels.append(f"{post['platform'][:2]}:{str(post.get('external_id') or '')[:6]}")
                # last metric for this post
                last = 0
                for m in reversed(metrics):
                    if m.get("post_external_id") == post.get("external_id"):
                        last = int(m.get("views") or m.get("likes") or 0)
                        break
                vals.append(last)
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.barh(labels, vals, color="#3b82f6")
            ax.set_title("Recent posts — views/likes snapshot")
            fig.tight_layout()
            p = self.chart_dir / "posts_snapshot.png"
            fig.savefig(p, dpi=120)
            plt.close(fig)
            paths["posts_snapshot"] = str(p)

        return paths

    def summary_for_dashboard(self) -> dict[str, Any]:
        metrics = db.recent_metrics(days=7)
        totals = {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        by_platform: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for m in metrics:
            for k in totals:
                totals[k] += int(m.get(k) or 0)
                by_platform[m["platform"]][k] += int(m.get(k) or 0)
        charts = {
            name: str(self.chart_dir / f"{name}.png")
            for name in ("engagement_by_platform", "likes_timeseries", "posts_snapshot")
            if (self.chart_dir / f"{name}.png").exists()
        }
        return {
            "totals": totals,
            "by_platform": {k: dict(v) for k, v in by_platform.items()},
            "charts": charts,
            "sample_count": len(metrics),
        }
