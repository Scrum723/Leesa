# Social Media Liaison Agent — Doc Weather

Monitors a video inbox, generates viral captions with **SpaceXAI (xAI)**, posts daily to **X, Instagram, TikTok, and YouTube**, notifies fans, engages comments, runs continuous account monitoring with alerts, and serves a simple web dashboard for accounts + per-platform settings + analytics.

**Brand:** Doc Weather / Charles Clottin · CTA: https://linktr.ee/URP  
**Companion:** `~/stream-chat-agent` (live chat), `weather-viral-posts` skill (nightly forecast packages)

## Features

| Module | What it does |
|--------|----------------|
| **Video watcher** | Watches `inbox/` (configurable) for new `.mp4`/`.mov` etc., settles file size, queues jobs |
| **Content AI** | Titles, descriptions, hashtags per platform via SpaceXAI |
| **Poster** | Posts to X / IG Reels / TikTok / YouTube Shorts using official APIs |
| **Fan notify** | Follow-up tweets, IG notify log, YT `notifySubscribers`, TikTok log |
| **Engagement** | Polls comments, AI/template replies, spam/negative heuristics |
| **Analytics** | Collects metrics, writes PNG charts + daily markdown reports |
| **Away monitor** | High-engagement + error alerts → macOS notifications + optional webhook |
| **Dashboard** | Accounts, platform response settings, queue, posts, analytics, alerts |
| **Ops** | APScheduler (daily post + analytics), rotating logs, JSONL events, SQLite |

## Mac desktop app + Railway dashboard

| Piece | What it is |
|-------|------------|
| **Mac app** | `Desktop/Doc Weather Liaison.app` or DMG `Doc Weather Liaison-1.0.0-arm64.dmg` |
| **Double-click launcher** | `Launch Doc Weather Liaison.command` in this repo |
| **Railway control room** | https://social-media-liaison-production.up.railway.app |
| **Content folder** | `Desktop/Doc Weather Content/` (videos + articles + bundles) |

Rebuild the Mac package:

```bash
cd ~/social-media-liaison/mac-app
npm install
npm run dist
```

## Content library (videos + writing)

See **[docs/CONTENT_LIBRARY.md](docs/CONTENT_LIBRARY.md)**.

```
Doc Weather Content/
  videos/ready/     finished clips
  articles/ready/   finished writing (.md/.txt)
  bundles/<slug>/   video + insight.md + meta.yaml  ← best for mixed posts
```

## Quick start (Python agent)

```bash
cd ~/social-media-liaison
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — leave DRY_RUN=true until credentials are ready
python run.py
```

Local dashboard: **http://127.0.0.1:8787** · Railway: production URL above

### Common commands

```bash
# Dry-run full agent (watcher + schedule + dashboard)
python run.py --dry-run

# Only scan inbox into queue
python run.py --scan

# Post next queued video now (respects DRY_RUN)
python run.py --post-now

# Generate analytics report now
python run.py --analytics-now

# Dashboard only (agent not scheduling)
python run.py --dashboard-only

# Live mode when ready
python run.py --live
```

### Drop videos here

Default inbox: `~/social-media-liaison/inbox/`  

Or set in `.env`:

```env
VIDEO_INBOX=/Users/charlesclottin/Desktop/shorts to upload
```

Daily post time defaults to **10:00 America/New_York** (`config.yaml` → `schedule.daily_post_time`).

## Configuration

| File | Purpose |
|------|---------|
| `.env` | API keys, DRY_RUN, inbox path, dashboard port |
| `config.yaml` | Brand, schedule, per-platform defaults, watcher limits |
| Dashboard → Platform Settings | Live overlay for reply mode, hashtags, enable flags |
| `data/liaison.db` | Jobs, posts, metrics, accounts, alerts |
| `logs/liaison.log` | Rotating human logs |
| `logs/events.jsonl` | Machine-readable event trail |

## Architecture

```
inbox/ ──► VideoWatcher ──► SQLite queue
                              │
                    daily schedule / post-now
                              ▼
              ContentGenerator (SpaceXAI)
                              ▼
         X · Instagram · TikTok · YouTube clients
                              ▼
              notify fans · archive file
                              │
         EngagementMonitor ◄──┘  (comments + replies)
         AnalyticsModule        (metrics + charts)
         AlertService           (macOS + webhook)
         Flask dashboard        (:8787)
```

## Safety defaults

- **`DRY_RUN=true`** until you set credentials and pass a dry-run post  
- Max posts/day (`watcher.max_posts_per_day`, default 3)  
- Per-user reply cooldowns and per-platform reply hour caps  
- Errors create alerts; partial multi-platform failures mark job `partial`  

## Platform honesty

See [docs/PLATFORMS.md](docs/PLATFORMS.md). Instagram Reels often need a public video URL or resumable upload support; TikTok/YouTube require developer app approval and OAuth.

## Skill / Grok

Skill path: `~/.grok/skills/social-media-liaison/SKILL.md`  
Slash: `/social-media-liaison`

---

Stay accurate. Stay informed.
