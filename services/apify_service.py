import os
import httpx
from typing import Optional

APIFY_TOKEN = os.getenv("APIFY_TOKEN")

ACTOR_IDS = {
    "tiktok":    "apidojo~tiktok-scraper",
    "instagram": "apify~instagram-post-scraper",   # fixed: correct actor
    "x":         "quacker~twitter-scraper",
}


# ── Normalizers ───────────────────────────────────────────────────────────────

def _norm_tiktok(item: dict) -> dict:
    author = item.get("authorMeta") or {}
    video  = item.get("videoMeta")  or {}
    vid_id = item.get("id", "")
    uname  = author.get("name", "")
    return {
        "id":        vid_id,
        "url":       item.get("webVideoUrl") or f"https://www.tiktok.com/@{uname}/video/{vid_id}",
        "views":     item.get("playCount", 0),
        "likes":     item.get("diggCount", 0),
        "comments":  item.get("commentCount", 0),
        "shares":    item.get("shareCount", 0),
        "caption":   item.get("text") or item.get("desc", ""),
        "posted_at": item.get("createTimeISO", ""),
        "duration":  video.get("duration", 0) if isinstance(video, dict) else 0,
    }


def _norm_instagram(item: dict) -> dict:
    # apify~instagram-post-scraper field names (confirmed from live test)
    return {
        "id":        item.get("id", ""),
        "url":       item.get("url") or f"https://instagram.com/p/{item.get('shortCode','')}",
        "views":     item.get("videoViewCount") or item.get("videoPlayCount") or 0,
        "likes":     item.get("likesCount") or 0,
        "comments":  item.get("commentsCount") or 0,
        "shares":    0,
        "caption":   item.get("caption") or item.get("alt") or "",
        "posted_at": item.get("timestamp") or item.get("takenAt") or "",
        "duration":  item.get("videoDuration") or 0,
        "type":      item.get("type", ""),
    }


def _norm_x(item: dict) -> dict:
    return {
        "id":        item.get("id") or item.get("tweet_id", ""),
        "url":       item.get("url") or item.get("tweetUrl", ""),
        "views":     item.get("viewCount") or item.get("views") or 0,
        "likes":     item.get("likeCount") or item.get("favorites") or 0,
        "comments":  item.get("replyCount") or item.get("replies") or 0,
        "shares":    item.get("retweetCount") or item.get("retweets") or 0,
        "caption":   item.get("text") or item.get("full_text") or "",
        "posted_at": item.get("createdAt") or item.get("created_at") or "",
        "duration":  0,
    }


NORMALIZERS = {
    "tiktok":    _norm_tiktok,
    "instagram": _norm_instagram,
    "x":         _norm_x,
}


# ── Input builders ────────────────────────────────────────────────────────────

def _build_input(platform: str, username: str, limit: int) -> dict:
    clean = username.lstrip("@")
    if platform == "tiktok":
        return {
            "profiles":             [f"https://www.tiktok.com/@{clean}"],
            "maxItems":             limit,
            "resultsPerPage":       limit,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        }
    if platform == "instagram":
        # apify~instagram-post-scraper expects username as array
        return {
            "username":     [clean],
            "resultsLimit": limit,
        }
    if platform == "x":
        return {
            "searchTerms": [f"from:{clean}"],
            "maxItems":    limit,
            "queryType":   "Latest",
        }
    raise ValueError(f"منصة غير مدعومة: {platform}")


# ── Main function ─────────────────────────────────────────────────────────────

async def fetch_social_media(platform: str, username: str, limit: int = 30) -> dict:
    platform = platform.lower().strip()
    if platform not in ACTOR_IDS:
        raise ValueError(f"المنصة '{platform}' غير مدعومة. الخيارات: tiktok, instagram, x")

    # X/Twitter warning: free Apify plan returns limited or empty results
    if platform == "x":
        raise RuntimeError(
            "X (Twitter) غير متاح حالياً — Twitter قيّد الـ scraping على الخطة المجانية. "
            "استخدمي TikTok أو Instagram."
        )

    actor_id  = ACTOR_IDS[platform]
    normalize = NORMALIZERS[platform]
    run_input = _build_input(platform, username, limit)

    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            url,
            json=run_input,
            params={"token": APIFY_TOKEN},
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(f"Apify error {response.status_code}: {response.text[:400]}")

        raw = response.json()

        if not isinstance(raw, list):
            raise RuntimeError(f"استجابة غير متوقعة من Apify: {str(raw)[:200]}")

        # Filter out error objects
        items = [r for r in raw if isinstance(r, dict) and "error" not in r]

        if len(items) == 0:
            if platform == "instagram":
                raise RuntimeError(
                    "لم يتم العثور على منشورات — تأكدي أن الحساب عام وأن اسم المستخدم صحيح"
                )
            raise RuntimeError("لم يتم العثور على منشورات — تأكدي من اسم الحساب")

        posts = [normalize(item) for item in items]

        return {
            "platform": platform,
            "username": username.lstrip("@"),
            "posts":    posts,
            "count":    len(posts),
        }


# ── Legacy wrapper ────────────────────────────────────────────────────────────

async def fetch_tiktok_videos(
    hashtag: Optional[str] = None,
    username: Optional[str] = None,
    max_items: int = 50,
):
    if username:
        result = await fetch_social_media("tiktok", username, max_items)
        return result["posts"]

    if hashtag:
        tag       = hashtag.lstrip("#")
        actor     = ACTOR_IDS["tiktok"]
        url       = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
        run_input = {
            "hashtags":             [tag],
            "maxItems":             max_items,
            "resultsPerPage":       max_items,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=run_input, params={"token": APIFY_TOKEN})
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Apify error {response.status_code}: {response.text[:400]}")
            raw = response.json()
            items = [r for r in raw if isinstance(r, dict) and "error" not in r]
            if not items:
                raise RuntimeError("لم يتم العثور على فيديوهات لهذا الهاشتاق")
            return [_norm_tiktok(item) for item in items]

    raise ValueError("يجب تحديد username أو hashtag")
