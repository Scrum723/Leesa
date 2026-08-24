# YouTube OAuth for LEESA (fix 403 / access_denied)

## What that Google screen means

**Social Medi Managers Agent** is your Google Cloud OAuth app. It is in **Testing** mode and has **not** completed Google’s public verification.

Until you either:

1. Add your Google account as a **Test user**, or  
2. Complete full Google verification (not needed for personal channel use),

Google shows **403 access_denied** or blocks Continue.

The scary lines (“permanently delete your YouTube videos”) came from an overly broad scope (`youtube.force-ssl`). LEESA now requests **upload only**.

## Fix checklist (do in order)

### 1. Google Cloud Console → correct project
Project that owns client ID:
`222633675340-20mcd51pq9p1nd8u8v6ut43btq17k9rd.apps.googleusercontent.com`

### 2. Enable API
**APIs & Services → Library → YouTube Data API v3 → Enable**

### 3. OAuth consent screen
**APIs & Services → OAuth consent screen**

- User type: **External**
- Publishing status: **Testing** (OK for your own channel)
- App name: can fix typo to “Social Media Managers Agent” later
- **Test users → Add users** → add the **exact** Gmail that owns WeatherWorldCC / YouTube Studio  
  Example: whatever account you use at studio.youtube.com

### 4. Scopes on consent screen
Add (if asked):

- `https://www.googleapis.com/auth/youtube.upload`

Do **not** require `youtube.force-ssl` for basic Shorts upload.

### 5. OAuth client
**Credentials → OAuth 2.0 Client IDs**

- Type: **Desktop app**
- Client ID / secret must match `data/youtube_client_secrets.json`

### 6. Run auth on your Mac
```bash
cd ~/social-media-liaison
source .venv/bin/activate
python scripts/youtube_auth.py
```

On the Google screen:

1. Choose the **test user** account (same as step 3)
2. If Google warns “unverified app” → **Advanced** → **Go to Social Medi Managers Agent (unsafe)**  
   (Normal for Testing apps you own)
3. Review permissions → **Continue**
4. Confirm `data/youtube_token.json` was created

## Still failing?

| Symptom | Cause |
|---------|--------|
| 403 access_denied | Account not a Test user, or wrong Google account |
| App not verified | Click Advanced → continue (Testing app) |
| redirect_uri_mismatch | Client must be Desktop type; re-download secrets |
| API not enabled | Enable YouTube Data API v3 |

## Do you need full Google verification?

**No** — not to upload to your own WeatherWorldCC channel while the app is in Testing with you as a test user.

Full verification is only for letting **random public users** authorize the app.
