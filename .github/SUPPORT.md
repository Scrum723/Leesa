# LEESA support

**LEESA** = Doc Weather Social Media Liaison (Charles Clottin).

## Get help

1. Check [legal & policies](https://social-media-liaison-production.up.railway.app/legal)
2. Open a GitHub Issue with platform + dry-run status + redacted logs
3. Do **not** paste API tokens or `.env` contents

## Automation that backs support

| Workflow | Purpose |
|----------|---------|
| `Python CI` | Lint + smoke tests on every push/PR |
| `CodeQL` | Security scanning (Python, JS/TS, Actions) |
| `Dependency Review` | Flag risky dependency changes on PRs |
| `Greetings` | Welcome first-time issues/PRs |
| `Stale` | Clean inactive issues/PRs |
| `Manual health check` | On-demand smoke + Railway ping |
| `SLSA generator` | Existing supply-chain workflow |

## What we intentionally did **not** add

Templates that do not match this repo (so CI does not fail for no reason):

- Java / Maven setup (LEESA is Python)
- Hugo site deploy
- Next.js GitHub Pages deploy
- Armory Cloud deploy

Those can be added later if LEESA gains those stacks.
