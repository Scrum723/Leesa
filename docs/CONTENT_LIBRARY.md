# Content Library — Videos + Writing (Doc Weather)

One library on your Mac. The **Mac app** watches it; the **Railway dashboard** shows queue, posts, and settings.

## Recommended root

```
~/Desktop/Doc Weather Content/
```

(Created for you. You can still drop files in `Ready to Post` — both work.)

## Layout

```
Doc Weather Content/
├── README.txt                 ← quick reminder
├── videos/
│   ├── inbox/                 ← rough exports from CapCut / phone
│   ├── ready/                 ← final clips ready to schedule/post
│   └── posted/                ← agent archives after success
├── articles/
│   ├── inbox/                 ← drafts you’re still writing
│   ├── ready/                 ← finished pieces (.md / .txt)
│   └── posted/
├── bundles/                   ← BEST for “clip + my insight”
│   ├── _TEMPLATE/
│   │   ├── video.mp4          (optional if article-only)
│   │   ├── insight.md         (your writing / personal take)
│   │   └── meta.yaml          (title, platforms, tags)
│   └── 2026-07-31-weekend-storm/
│       ├── video.mp4
│       ├── insight.md
│       └── meta.yaml
└── assets/                    ← thumbnails, stills (optional)
```

## What each type becomes on socials

| You drop | Agent treats as | Typical platforms |
|----------|-----------------|-------------------|
| `videos/ready/*.mp4` | Short / Reel / Shorts | X, Instagram, TikTok, YouTube |
| `articles/ready/*.md` | Text post / thread / caption | X (thread or long post), IG caption post if supported, YT community-style text logged |
| `bundles/<slug>/` | **Video + your written insight** | Video posts use `insight.md` as caption/description source; X can also notify with a text follow-up |

## Naming rules (keep it consistent)

1. **Videos:** `topic-short-hint.mp4`  
   Example: `wny-weekend-thunder-threat.mp4`
2. **Articles:** `topic-short-hint.md`  
   Example: `why-lake-effect-still-matters.md`
3. **Bundles:** folder `YYYY-MM-DD-short-slug`  
   Example: `2026-07-31-weekend-storm`
4. Prefer **spaces only in folder titles you want to read**; files use hyphens.

## `meta.yaml` (bundles)

```yaml
title_hint: "Weekend thunder returns to WNY"
platforms: [x, instagram, tiktok, youtube]
content_type: bundle   # video | article | bundle
tags: [WNY, Buffalo, severe]
cta: "https://linktr.ee/URP"
notes: "Recorded 7/30 evening — still accurate as of morning"
```

## `insight.md` tips

- First line can be `# Title` (used as title if meta empty)
- Next paragraphs = body / caption source
- End with CTA if you want: `Full links → https://linktr.ee/URP`
- Keep a short **hook** in the first 1–2 sentences (algo + humans)

## Workflow (seamless)

1. Export clip → `videos/inbox/` (or CapCut export)
2. Write take → `articles/inbox/` **or** put both in a new `bundles/…` folder
3. When ready to go live, move into `*/ready/` (or leave bundle folder complete)
4. Mac app / agent scans → queue appears in Railway dashboard
5. After post → files land in `*/posted/`

## Dashboard

- **Library** page lists videos, articles, and bundles the agent sees
- **Posts & Queue** is the scheduled/posted history
- Railway URL stays the “control room”; Mac app is the local content desk

Stay accurate. Stay informed.
