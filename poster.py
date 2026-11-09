"""
Watches an X (Twitter) account and reposts each new photo tweet to TikTok
as a swipeable photo post (carousel), with the tweet text as the caption.

Runs once per invocation (GitHub Actions calls it every ~5 minutes).

Flow per run:
  1. Ask X for tweets newer than the last one we handled (since_id).
  2. For each new tweet with photos: download the photos, convert to JPEG
     sized for TikTok, save them under docs/media/ (served by GitHub Pages).
  3. Commit + push, wait for GitHub Pages to serve the files.
  4. Tell TikTok to pull those image URLs and create a photo post on every
     connected TikTok account.
"""
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
MEDIA_DIR = ROOT / "docs" / "media"

X_USERNAME = (os.environ.get("X_USERNAME") or "bullish_hunter1").lstrip("@")
X_BEARER = os.environ["X_BEARER_TOKEN"]
TT_CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
TT_CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
# One refresh token per TikTok account, comma-separated
TT_REFRESH_TOKENS = [t.strip() for t in os.environ["TIKTOK_REFRESH_TOKENS"].split(",") if t.strip()]
# MEDIA_UPLOAD = lands in your TikTok inbox/drafts, tap to post (works before TikTok audit)
# DIRECT_POST  = posts straight to profile (public only after TikTok approves your app)
POST_MODE = (os.environ.get("POST_MODE") or "MEDIA_UPLOAD")
PRIVACY = (os.environ.get("PRIVACY_LEVEL") or "PUBLIC_TO_EVERYONE")  # DIRECT_POST only
# Public base URL where docs/ is served, e.g. https://yourname.github.io/x-to-tiktok
PAGES_BASE = os.environ["PAGES_BASE_URL"].rstrip("/")

X_API = "https://api.x.com/2"
TT_API = "https://open.tiktokapis.com/v2"


def log(*a):
    print(*a, flush=True)


# ---------------- state ----------------
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))


# ---------------- X ----------------
def x_get(path, params=None):
    r = requests.get(f"{X_API}{path}", params=params,
                     headers={"Authorization": f"Bearer {X_BEARER}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"X API {r.status_code}: {r.text}")
    return r.json()


def get_user_id(state):
    if state.get("x_user_id") and state.get("x_username") == X_USERNAME:
        return state["x_user_id"]
    uid = x_get(f"/users/by/username/{X_USERNAME}")["data"]["id"]
    state["x_user_id"], state["x_username"] = uid, X_USERNAME
    return uid


def fetch_new_tweets(uid, since_id):
    params = {
        "max_results": 5,
        "exclude": "retweets,replies",
        "expansions": "attachments.media_keys",
        "media.fields": "type,url",
        "tweet.fields": "created_at,note_tweet",
    }
    if since_id:
        params["since_id"] = since_id
    data = x_get(f"/users/{uid}/tweets", params)
    tweets = data.get("data", [])
    media = {m["media_key"]: m for m in data.get("includes", {}).get("media", [])}
    out = []
    for t in reversed(tweets):  # oldest first
        keys = t.get("attachments", {}).get("media_keys", [])
        photos = [media[k]["url"] for k in keys if k in media and media[k]["type"] == "photo"]
        text = t.get("note_tweet", {}).get("text") or t["text"]
        out.append({"id": t["id"], "text": text, "photos": photos})
    return out


def clean_caption(text):
    text = re.sub(r"\s*https://t\.co/\S+", "", text)  # drop X's media/short links
    return text.strip()


# ---------------- images ----------------
def prepare_image(url, dest):
    big = url + ("&" if "?" in url else "?") + "name=orig"
    r = requests.get(big, timeout=60)
    if r.status_code != 200:
        r = requests.get(url, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    # TikTok: JPEG/WebP, must fit within 1080x1920 (portrait) or 1920x1080 (landscape)
    box = (1920, 1080) if img.width > img.height else (1080, 1920)
    img.thumbnail(box, Image.LANCZOS)
    img.save(dest, "JPEG", quality=92)


def git_publish(msg):
    subprocess.run(["git", "add", "-A", "docs/media", "state.json"], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)


def wait_until_live(urls, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if all(requests.head(u, timeout=15).status_code == 200 for u in urls):
                return True
        except requests.RequestException:
            pass
        time.sleep(15)
    return False


# ---------------- TikTok ----------------
def tt_access_token(refresh_token):
    r = requests.post(f"{TT_API}/oauth/token/", data={
        "client_key": TT_CLIENT_KEY,
        "client_secret": TT_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"TikTok token refresh failed: {d}")
    if d.get("refresh_token") and d["refresh_token"] != refresh_token:
        log("NOTE: TikTok issued a new refresh token; update the TIKTOK_REFRESH_TOKENS secret.")
    return d["access_token"]


def tt_post_photos(access_token, image_urls, caption):
    title = caption.split("\n")[0][:90]
    post_info = {"title": title, "description": caption[:4000]}
    if POST_MODE == "DIRECT_POST":
        post_info.update({"privacy_level": PRIVACY, "disable_comment": False,
                          "auto_add_music": True})
    body = {
        "post_info": post_info,
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0,
                        "photo_images": image_urls},
        "post_mode": POST_MODE,
        "media_type": "PHOTO",
    }
    r = requests.post(f"{TT_API}/post/publish/content/init/", json=body,
                      headers={"Authorization": f"Bearer {access_token}",
                               "Content-Type": "application/json; charset=UTF-8"},
                      timeout=30)
    d = r.json()
    if d.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok post failed: {d}")
    return d["data"]["publish_id"]


def tt_status(access_token, publish_id):
    r = requests.post(f"{TT_API}/post/publish/status/fetch/", json={"publish_id": publish_id},
                      headers={"Authorization": f"Bearer {access_token}",
                               "Content-Type": "application/json; charset=UTF-8"}, timeout=30)
    return r.json().get("data", {}).get("status")


# ---------------- main ----------------
def main():
    state = load_state()
    uid = get_user_id(state)
    since = state.get("since_id")

    if not since:
        # First run: don't repost old tweets, just remember the newest one.
        latest = x_get(f"/users/{uid}/tweets", {"max_results": 5, "exclude": "retweets,replies"})
        if latest.get("data"):
            state["since_id"] = latest["data"][0]["id"]
        save_state(state)
        git_publish("init state")
        log("Initialized. Will repost tweets from now on.")
        return

    tweets = fetch_new_tweets(uid, since)
    if not tweets:
        log("No new tweets.")
        return

    jobs = []
    for t in tweets:
        state["since_id"] = t["id"]
        if not t["photos"]:
            log(f"Skip {t['id']}: no photos")
            continue
        urls = []
        for i, p in enumerate(t["photos"][:35], 1):
            name = f"{t['id']}_{i}.jpg"
            prepare_image(p, MEDIA_DIR / name)
            urls.append(f"{PAGES_BASE}/media/{name}")
        jobs.append((t, urls))

    save_state(state)
    git_publish(f"media for {len(jobs)} tweet(s)")
    if not jobs:
        return

    all_urls = [u for _, us in jobs for u in us]
    if not wait_until_live(all_urls):
        log("Images not live on GitHub Pages in time; will not post.")
        sys.exit(1)

    tokens = [tt_access_token(rt) for rt in TT_REFRESH_TOKENS]
    failed = False
    for t, urls in jobs:
        caption = clean_caption(t["text"])
        for n, tok in enumerate(tokens, 1):
            try:
                pid = tt_post_photos(tok, urls, caption)
                time.sleep(10)
                log(f"Tweet {t['id']} -> TikTok account {n}: {pid} ({tt_status(tok, pid)})")
            except Exception as e:
                failed = True
                log(f"Tweet {t['id']} -> TikTok account {n} FAILED: {e}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
