# LEESA Daily Audience Polls

Addresses the **19 Aug 2026 Daily Poll Execution Report** remediation list.

## What was broken (report context)

The Grok/X-Ads-only session could not post organic polls. **LEESA itself already has organic X OAuth 1.0a** when `X_ACCESS_TOKEN` + secret are set — that is the fix for priority #1 (organic X + native poll).

Instagram / TikTok / YouTube still lack native poll APIs in LEESA (honest skip + alert).

## Schedule (in-agent)

| Job | Time (America/New_York) |
|-----|-------------------------|
| Prepare + post X poll | **09:00** daily |
| Collect results | Every 15 minutes for polls past `results_due_at` (24h) |
| Video queue post | 10:00 |
| Analytics | 21:00 |

Configured in `config.yaml` → `schedule.daily_poll_time` / `polls.*`.

## Commands

```bash
cd ~/social-media-liaison && source .venv/bin/activate

# Dry-run safe if DRY_RUN=true
python run.py --poll-now
python run.py --poll-results-now
```

Dashboard: **Daily Polls** → “Post poll now”.

## Grok Automations (companion)

If you also want a Grok Automations reminder/report at 09:00 ET:

- **cadence:** `RRULE:FREQ=DAILY`
- **time_of_day:** `09:00`
- **timezone:** `America/New_York`
- **prompt:** run the five-step poll process via LEESA (`python run.py --poll-now` on the Mac agent, or dashboard Post poll now), then log connectivity + next-day results collection.

Prefer the **in-agent APScheduler** job as source of truth for posting; use Automations for human-readable reports if desired.

## Prepared poll (from 19 Aug report)

Question + 4 options are stored as `FALL_TRANSITION_POLL` in `src/polls/service.py` (options trimmed to X’s ~25-character limit). AI can regenerate daily when `XAI_API_KEY` is set.

## Metrics

After 24h, markdown reports write to `data/polls/poll_report_YYYY-MM-DD_<id>.md` with vote totals and option shares.
