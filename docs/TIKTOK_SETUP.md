# TikTok setup for LEESA

## Website / domain verification (fixes portal errors)

TikTok must be able to fetch a verification file or meta tag from your **public website URL**.

### Verification file content

```text
tiktok-developers-site-verification=IcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8
```

### Use one of these as your TikTok “Website URL”

| Host | URL to enter in TikTok Developer Portal |
|------|-----------------------------------------|
| **GitHub Pages (recommended)** | `https://scrum723.github.io/Leesa/` |
| **Railway dashboard** | `https://social-media-liaison-production.up.railway.app/` |

### File must open in a browser (plain text)

- Pages: https://scrum723.github.io/Leesa/tiktokIcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8.txt  
- Railway: https://social-media-liaison-production.up.railway.app/tiktokIcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8.txt  

Also embedded on the Pages homepage as:

```html
<meta name="tiktok-developers-site-verification" content="IcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8" />
```

### In TikTok for Developers

1. Open your app → **Basic information** / **Website**  
2. Set website URL to the Pages or Railway URL above  
3. Choose **File** verification (or Meta tag)  
4. Click **Verify**

## App review URLs (already live)

| Field | URL |
|-------|-----|
| Terms of Service | https://social-media-liaison-production.up.railway.app/legal/terms |
| Privacy Policy | https://social-media-liaison-production.up.railway.app/legal/privacy |
| Data Collection / deletion info | https://social-media-liaison-production.up.railway.app/legal/data-collection |

(Same pages also linked from https://scrum723.github.io/Leesa/)

## Credentials in LEESA (agent posting — not iOS OpenSDK)

| Env var | Status |
|---------|--------|
| `TIKTOK_CLIENT_KEY` | App client key |
| `TIKTOK_CLIENT_SECRET` | App secret |
| `TIKTOK_APP_ID` | App id |
| `TIKTOK_ACCESS_TOKEN` | **User** token after OAuth (still required to post) |
| `TIKTOK_REFRESH_TOKEN` | Optional |
| `TIKTOK_OPEN_ID` | Optional |

**iOS OpenSDK** is not part of LEESA. Domain verification + Content Posting / Login Kit web OAuth is.

## After verification succeeds

Complete Login Kit / Content Posting OAuth for your TikTok account, then set `TIKTOK_ACCESS_TOKEN` in `.env` and Railway variables.
