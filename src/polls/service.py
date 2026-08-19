"""Daily audience polls for Doc Weather / LEESA."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import db
from ..ai_content import ContentGenerator
from ..config import ROOT, Settings
from ..logging_setup import EventLog
from ..models import utcnow
from ..posting.orchestrator import PostingOrchestrator

log = logging.getLogger("liaison.polls")

# Prepared poll from 2026-08-19 report — options trimmed to X's ~25-char limit
FALL_TRANSITION_POLL = {
    "question": (
        "Milder temps + scattered showers over WNY — which part of fall are you most anticipating?"
    ),
    "options": [
        "Cooler highs (60s-70s)",
        "Fall foliage outdoors",
        "Lake-effect snow back",
        "Crisp low-humidity AM",
    ],
}


@dataclass
class PollDraft:
    question: str
    options: list[str]
    source: str = "template"


class PollService:
    def __init__(
        self,
        settings: Settings,
        orchestrator: PostingOrchestrator | None = None,
        events: EventLog | None = None,
    ) -> None:
        self.settings = settings
        self.orch = orchestrator or PostingOrchestrator(settings)
        self.events = events or EventLog()
        self.ai = ContentGenerator(settings)
        self.report_dir = ROOT / "data" / "polls"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _tz(self) -> ZoneInfo:
        name = (self.settings.config.get("schedule") or {}).get("timezone", "America/New_York")
        try:
            return ZoneInfo(name)
        except Exception:
            return ZoneInfo("America/New_York")

    def today_str(self) -> str:
        return datetime.now(self._tz()).date().isoformat()

    def generate_poll(self, weather_hint: str = "") -> PollDraft:
        """Generate a WNY-focused poll; falls back to prepared template."""
        poll_cfg = (self.settings.config.get("polls") or {})
        use_ai = bool(poll_cfg.get("ai_generate", True)) and self.ai.available

        if use_ai and self.ai._client:
            try:
                system = (
                    self.settings.brand.get("persona", "")
                    + "\nCreate ONE Twitter/X poll for Western NY weather fans. "
                    "Return ONLY JSON: {\"question\": str, \"options\": [str,str,str,str]}. "
                    "Question under 200 chars. Each option under 50 chars (X limit ~25 for some tiers; keep short). "
                    "Professional, engaging, no spam."
                )
                user = (
                    f"Brand: {self.settings.streamer_name}\n"
                    f"Weather context: {weather_hint or 'late summer transition into fall for Buffalo / WNY'}\n"
                    "Focus: local forecast interest, lake-effect, seasonal change."
                )
                resp = self.ai._client.chat.completions.create(
                    model=self.settings.xai_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.8,
                    max_tokens=400,
                )
                raw = (resp.choices[0].message.content or "").strip()
                data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
                q = str(data.get("question") or "").strip()
                opts = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
                opts = [_trim_option(o) for o in opts[:4]]
                if q and len(opts) >= 2:
                    while len(opts) < 4:
                        opts.append("Not sure / watching the maps")
                    return PollDraft(question=q[:280], options=opts[:4], source="ai")
            except Exception as e:
                log.warning("AI poll generation failed, using template: %s", e)

        # Prefer prepared report poll for known transition season
        return PollDraft(
            question=FALL_TRANSITION_POLL["question"],
            options=[_trim_option(o) for o in FALL_TRANSITION_POLL["options"]],
            source="template",
        )

    def prepare_and_post(
        self,
        *,
        force: bool = False,
        weather_hint: str = "",
        draft: PollDraft | None = None,
    ) -> dict[str, Any]:
        """Steps 1–3: generate, store, post to X (native poll)."""
        run_date = self.today_str()
        existing = db.poll_for_date(run_date)
        if existing and existing.get("status") in {"posted", "collected"} and not force:
            return {"ok": True, "skipped": True, "reason": "already_posted_today", "poll": existing}

        draft = draft or self.generate_poll(weather_hint=weather_hint)
        poll_id = db.create_poll(run_date, draft.question, draft.options, platform="x", status="prepared")
        self.events.write(
            "poll_prepared",
            poll_id=poll_id,
            question=draft.question,
            options=draft.options,
            source=draft.source,
        )

        x = self.orch.clients.get("x")
        if not x or not x.is_configured():
            err = "X organic credentials not configured (need OAuth 1.0a user tokens)"
            db.update_poll(poll_id, status="failed", error=err)
            db.create_alert("error", "poll", "Daily poll failed: X not connected", err, platform="x")
            return {"ok": False, "poll_id": poll_id, "error": err}

        # Duration: 24h in minutes
        duration_minutes = int((self.settings.config.get("polls") or {}).get("duration_minutes", 1440))
        result = x.create_poll(
            text=draft.question,
            options=draft.options,
            duration_minutes=duration_minutes,
        )
        if not result.success:
            db.update_poll(poll_id, status="failed", error=result.error or "post failed")
            db.create_alert(
                "error",
                "poll",
                "Daily poll post failed on X",
                result.error or "",
                platform="x",
            )
            self.events.write("poll_post_failed", poll_id=poll_id, error=result.error)
            return {"ok": False, "poll_id": poll_id, "error": result.error, "dry_run": result.dry_run}

        due = (datetime.now(self._tz()) + timedelta(minutes=duration_minutes)).isoformat()
        db.update_poll(
            poll_id,
            status="posted",
            external_id=result.external_id,
            url=result.url,
            posted_at=utcnow(),
            results_due_at=due,
            error="",
        )
        self.events.write(
            "poll_posted",
            poll_id=poll_id,
            external_id=result.external_id,
            url=result.url,
            dry_run=result.dry_run,
        )
        return {
            "ok": True,
            "poll_id": poll_id,
            "url": result.url,
            "external_id": result.external_id,
            "dry_run": result.dry_run,
            "question": draft.question,
            "options": draft.options,
        }

    def collect_due_results(self) -> list[dict[str, Any]]:
        """Step 4–5: fetch poll results and write report."""
        due = db.polls_due_for_results()
        out: list[dict[str, Any]] = []
        x = self.orch.clients.get("x")
        for poll in due:
            poll_id = int(poll["id"])
            ext = poll.get("external_id") or ""
            if not x or not ext or ext.startswith("dry_"):
                # Synthetic dry-run results
                options = json.loads(poll.get("options_json") or "[]")
                fake = {
                    "options": [{"label": o, "votes": 0, "position": i} for i, o in enumerate(options)],
                    "total_votes": 0,
                    "note": "dry_run_or_missing_client",
                }
                report = self._write_report(poll, fake)
                db.update_poll(
                    poll_id,
                    status="collected",
                    results_json=json.dumps(fake),
                    results_collected_at=utcnow(),
                    report_path=str(report),
                )
                out.append({"poll_id": poll_id, "ok": True, "dry_run": True, "report": str(report)})
                continue

            metrics = x.fetch_poll_results(ext)
            if not metrics.get("ok"):
                db.update_poll(poll_id, error=metrics.get("error") or "results fetch failed")
                out.append({"poll_id": poll_id, "ok": False, "error": metrics.get("error")})
                continue

            report = self._write_report(poll, metrics)
            db.update_poll(
                poll_id,
                status="collected",
                results_json=json.dumps(metrics),
                results_collected_at=utcnow(),
                report_path=str(report),
                error="",
            )
            self.events.write("poll_results_collected", poll_id=poll_id, total=metrics.get("total_votes"))
            out.append({"poll_id": poll_id, "ok": True, "report": str(report), "metrics": metrics})
        return out

    def _write_report(self, poll: dict[str, Any], metrics: dict[str, Any]) -> Path:
        run_date = poll.get("run_date") or self.today_str()
        path = self.report_dir / f"poll_report_{run_date}_{poll['id']}.md"
        options = metrics.get("options") or []
        total = int(metrics.get("total_votes") or 0)
        lines = [
            f"# Daily Poll Report — {run_date}",
            "",
            f"**Brand:** {self.settings.streamer_name}",
            f"**Platform:** {poll.get('platform')}",
            f"**Status:** {poll.get('status')}",
            f"**URL:** {poll.get('url') or 'n/a'}",
            "",
            "## Question",
            "",
            poll.get("question") or "",
            "",
            "## Results",
            "",
            f"Total votes: **{total}**",
            "",
            "| Option | Votes | Share |",
            "|--------|------:|------:|",
        ]
        for o in options:
            label = o.get("label") or o.get("position")
            votes = int(o.get("votes") or 0)
            share = f"{(100.0 * votes / total):.1f}%" if total else "0%"
            lines.append(f"| {label} | {votes} | {share} |")
        lines += [
            "",
            "## Follow-up ideas",
            "",
            "- Short segment on the winning option with WNY meteorological context",
            "- Skew-T / surface map graphic for the result discussion",
            "- Cross-post summary thread with linktr.ee/URP",
            "",
            "Stay accurate. Stay informed.",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


def _trim_option(text: str, limit: int = 25) -> str:
    """X poll options are limited (~25 chars on many access tiers)."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    # Prefer cutting at word boundary
    cut = t.rfind(" ", 0, limit - 1)
    if cut < 8:
        cut = limit - 1
    return t[:cut].rstrip() + "..."


