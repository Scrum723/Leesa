# Platform APIs — Social Media Liaison

Honest capability matrix for Doc Weather / Charles Clottin.

| Platform | Video post | Fan notify | Comment reply | Metrics | Notes |
|----------|------------|------------|---------------|---------|-------|
| **X** | Yes (media upload + tweet) | Follow-up/quote tweet | Yes (reply tweets) | public_metrics | Needs elevated write + media |
| **Instagram** | Reels via Graph API | Story CTA logged / future story post | Yes (comment replies) | Insights | Business/Creator + Page token; Reels prefer public `video_url` or resumable upload |
| **TikTok** | Content Posting API | Logged (no mass DM API) | Limited (app scopes) | video/query | App review required for direct post |
| **YouTube** | Data API v3 upload (Shorts) | `notifySubscribers` on upload | Yes (comment replies) | statistics | OAuth desktop flow once |

## Setup checklists

### X
1. Developer portal → app with OAuth 1.0a user context  
2. Keys: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`  
3. Scopes: tweet read/write, media upload  

### Instagram
1. Meta app → Instagram Graph API  
2. Facebook Page linked to Instagram Business/Creator  
3. Long-lived Page token with `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_insights`  
4. `INSTAGRAM_BUSINESS_ACCOUNT_ID` + `INSTAGRAM_ACCESS_TOKEN`  
5. For local files without public URL, host temporarily (S3/R2) or enable resumable upload  

### TikTok
1. TikTok for Developers → Content Posting API  
2. OAuth user token → `TIKTOK_ACCESS_TOKEN`  
3. Audit/approve `video.publish` as required  

### YouTube
1. Google Cloud project → YouTube Data API v3  
2. OAuth client (desktop) secrets JSON  
3. First run may open browser for consent; token saved to `data/youtube_token.json`  
4. Or set `YOUTUBE_CLIENT_ID` / `SECRET` / `REFRESH_TOKEN`  

## Related projects
- `~/stream-chat-agent` — live chat (Twitch/FB) + X promos  
- `weather-viral-posts` skill — content generation packages  
