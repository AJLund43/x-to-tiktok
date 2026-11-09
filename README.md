# X → TikTok photo reposter

Every ~5 min it checks the X account. When a new tweet has pictures, it posts them to TikTok as a swipeable photo post, using the tweet text as the caption. It runs free on GitHub Actions, so you don't need to keep your computer on.

## Setup (about 30 min, one time)

### 1. GitHub repo
1. Create a **public** GitHub repo named `x-to-tiktok` and upload everything in this folder.
2. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/docs`.
   Your image URL will be `https://YOURNAME.github.io/x-to-tiktok`.

### 2. X API (to read the tweets)
1. Go to console.x.com, create a project and app, and add a few dollars of credit. Each new tweet read costs about half a cent.
2. Copy the app's **Bearer Token**.

### 3. TikTok developer app (to post)
1. Go to developers.tiktok.com, create an app, and add the **Login Kit** and **Content Posting API** products.
2. Scopes: `user.info.basic`, `video.upload`, `video.publish`.
3. Login Kit redirect URI: `https://YOURNAME.github.io/x-to-tiktok/callback.html`
4. Under Content Posting API, **verify the URL prefix** `https://YOURNAME.github.io/x-to-tiktok/`. TikTok gives you a file to upload into `docs/`.
5. Under Sandbox/Target users, add your TikTok account(s).
6. Copy the **Client key** and **Client secret**.

### 4. Connect your TikTok account(s)
```
pip install requests
python get_tiktok_token.py
```
Run it once for each TikTok account, logging into the right account each time. Save each refresh token.

### 5. Add secrets to the repo
Settings → Secrets and variables → Actions

**Secrets:**
| Name | Value |
|---|---|
| `X_BEARER_TOKEN` | from step 2 |
| `TIKTOK_CLIENT_KEY` | from step 3 |
| `TIKTOK_CLIENT_SECRET` | from step 3 |
| `TIKTOK_REFRESH_TOKENS` | token1,token2 (comma-separated) |

**Variables:**
| Name | Value |
|---|---|
| `X_USERNAME` | the account to watch (default `bullish_hunter1`) |
| `PAGES_BASE_URL` | `https://YOURNAME.github.io/x-to-tiktok` |
| `POST_MODE` | `MEDIA_UPLOAD` (default) or `DIRECT_POST` |

### 6. Start it
Go to Actions → *X to TikTok* → **Run workflow**. The first run only saves where it's starting from, so old tweets don't get reposted. After that it runs on its own.

## Post modes
- **MEDIA_UPLOAD (default):** the post shows up in your TikTok inbox already loaded with both pictures and the caption. You tap it to publish. This works right away.
- **DIRECT_POST:** posts publicly with no tap needed, but only after TikTok approves (audits) your app. Until then TikTok forces these posts to private. Apply for the audit in the developer portal, then set `POST_MODE` to `DIRECT_POST`.

## Notes
- Tweets with no pictures, replies and retweets are skipped.
- `t.co` links are removed from the caption.
- If a run fails, open the Actions tab to see the error.
