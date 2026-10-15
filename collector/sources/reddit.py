"""
New posts from data-career subreddits, via Reddit's official OAuth API.

OPTIONAL: Reddit now reviews new API access requests, so this source switches on
only once REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are set. Until then it is
skipped and logged, and the other sources run normally.

Only post metadata is stored (title, score, comment count, time). Usernames are
not collected.
"""
from datetime import datetime, timezone

from collector.db import now_utc, upsert
from collector.sources.base import Source

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com/r/{sub}/new"


class RedditPosts(Source):
    name = "reddit"

    def is_configured(self):
        if self.settings.reddit_client_id and self.settings.reddit_client_secret:
            return True, ""
        return False, "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set (optional source)"

    def _token(self) -> str:
        resp = self.session.post(
            TOKEN_URL,
            auth=(self.settings.reddit_client_id, self.settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.settings.reddit_user_agent},
            timeout=self.settings.request_timeout,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def extract(self):
        headers = {"Authorization": f"bearer {self._token()}", "User-Agent": self.settings.reddit_user_agent}
        raw = []
        for sub in self.settings.subreddits:
            resp = self.session.get(API.format(sub=sub), headers=headers,
                                    params={"limit": self.settings.posts_per_subreddit},
                                    timeout=self.settings.request_timeout)
            resp.raise_for_status()
            raw.append(resp.json())
        return raw

    def transform(self, raw):
        seen_at = now_utc()
        rows = []
        for listing in raw:
            for child in listing.get("data", {}).get("children", []):
                p = child["data"]
                rows.append({
                    "post_id": p["id"],
                    "subreddit": p["subreddit"],
                    "title": p["title"],
                    "flair": p.get("link_flair_text"),
                    "score": p.get("score"),
                    "num_comments": p.get("num_comments"),
                    "created_at": datetime.fromtimestamp(p["created_utc"], tz=timezone.utc).isoformat(),
                    "permalink": "https://www.reddit.com" + p.get("permalink", ""),
                    "first_seen_at": seen_at,
                    "last_seen_at": seen_at,
                })
        return {"reddit_posts": rows}

    def load(self, conn, tables):
        return upsert(conn, "reddit_posts", tables["reddit_posts"], key=("post_id",),
                      keep_on_update=("first_seen_at",))
