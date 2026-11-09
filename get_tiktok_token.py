"""
One-time helper: connect a TikTok account and print its refresh token.
Run once per TikTok account (log into the right account in your browser each time).

  python get_tiktok_token.py
"""
import secrets
import urllib.parse

import requests

client_key = input("TikTok client key: ").strip()
client_secret = input("TikTok client secret: ").strip()
redirect_uri = input("Redirect URI (e.g. https://yourname.github.io/x-to-tiktok/callback.html): ").strip()

url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": client_key,
    "scope": "user.info.basic,video.upload,video.publish",
    "response_type": "code",
    "redirect_uri": redirect_uri,
    "state": secrets.token_hex(8),
})
print("\n1) Open this link, log into the TikTok account you want, and approve:\n")
print(url)
code = input("\n2) Paste the code shown on the callback page: ").strip()

r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
    "client_key": client_key,
    "client_secret": client_secret,
    "code": urllib.parse.unquote(code),
    "grant_type": "authorization_code",
    "redirect_uri": redirect_uri,
}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
d = r.json()
if "refresh_token" not in d:
    raise SystemExit(f"Failed: {d}")
print("\nRefresh token (save this):\n")
print(d["refresh_token"])
