import os
import httpx
from typing import Optional

APIFY_TOKEN = os.getenv("APIFY_TOKEN")

ACTOR_IDS = {
    "tiktok":    "novi~tiktok-user-api",
    "instagram": "apify~instagram-post-scraper",
    "x":         "quacker~twitter-scraper",
}


# ── Normalizers ───────────────────────────────────────────────────────────────

def _norm_tiktok(item: dict) -> dict:
    # Support both old server-API schema (statistics/author/video) and
    # free-scraper schema (top-level fields + authorMeta/videoMeta)
    stats      = item.get("statistics") or {}
    author     = item.get("author") or item.get("authorMeta") or {}
    video_meta = item.get("video") or item.get("videoMeta") or {}
    vid_id     = item.get("aweme_id") or item.get("id", "")
    uname      = (author.get("unique_id") or author.get("uniqueId")
                  or author.get("name") or "")
    ts         = item.get("create_time") or item.get("createTime") or 0
    url        = (item.get("share_url") or item.get("webVideoUrl")
                  or f"https://www.tiktok.com/@{uname}/video/{vid_id}")
    duration   = (video_meta.get("duration", 0)
                  if isinstance(video_meta, dict) else 0)
    return {
        "id":        vid_id,
        "url":       url,
        "views":     (stats.get("play_count") or stats.get("playCount")
                      or item.get("playCount") or 0),
        "likes":     (stats.get("digg_count") or stats.get("diggCount")
                      or item.get("diggCount") or 0),
        "comments":  (stats.get("comment_count") or stats.get("commentCount")
                      or item.get("commentCount") or 0),
        "shares":    (stats.get("share_count") or stats.get("shareCount")
                      or item.get("shareCount") or 0),
        "caption":   item.get("desc") or item.get("text") or "",
        "posted_at": str(ts),
        "duration":  duration,
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
            "username": clean,
            "maxItems": max(20, limit),
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
            body = response.text[:400]
            if "not-enough-usage" in body or "paid-actor" in body:
                raise RuntimeError("not-enough-usage-to-run-paid-actor")
            raise RuntimeError(f"Apify error {response.status_code}: {body}")

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
        for p in posts:
            p["platform"] = platform

        return {
            "platform": platform,
            "username": username.lstrip("@"),
            "posts":    posts,
            "count":    len(posts),
        }


# ── Comments fetcher ─────────────────────────────────────────────────────────

COMMENT_ACTOR_IDS = {
    "tiktok":    "clockworks~tiktok-comments-scraper",
    "instagram": "apify~instagram-comment-scraper",
}


def _norm_tiktok_comment(item: dict) -> dict:
    return {
        "text":   item.get("text") or item.get("comment") or "",
        "likes":  item.get("diggCount") or item.get("likes") or 0,
        "author": item.get("uniqueId") or item.get("user") or "",
    }


def _norm_instagram_comment(item: dict) -> dict:
    return {
        "text":   item.get("text") or item.get("comment") or "",
        "likes":  item.get("likesCount") or 0,
        "author": item.get("ownerUsername") or "",
    }


_COMMENT_NORMALIZERS = {
    "tiktok":    _norm_tiktok_comment,
    "instagram": _norm_instagram_comment,
}


async def fetch_comments(platform: str, video_urls: list[str], max_per_video: int = 50) -> list[dict]:
    platform = platform.lower().strip()
    if platform not in COMMENT_ACTOR_IDS:
        raise ValueError(f"المنصة '{platform}' غير مدعومة للكومنتس")
    if not video_urls:
        return []

    actor_id  = COMMENT_ACTOR_IDS[platform]
    normalize = _COMMENT_NORMALIZERS[platform]

    if platform == "tiktok":
        run_input = {"postURLs": video_urls[:10], "maxComments": max_per_video}
    else:
        run_input = {"directUrls": video_urls[:10], "resultsLimit": max_per_video * len(video_urls[:10])}

    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            url,
            json=run_input,
            params={"token": APIFY_TOKEN},
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Apify comments error {response.status_code}: {response.text[:400]}")
        raw = response.json()
        if not isinstance(raw, list):
            return []
        items = [r for r in raw if isinstance(r, dict) and "error" not in r]
        return [normalize(item) for item in items if item.get("text") or item.get("comment")]


def fetch_comments_sync(
    platform: str,
    video_urls: list[str],
    max_per_video: int = 40,
) -> list[dict]:
    """
    Synchronous version of fetch_comments for use inside threadpool workers.
    Uses httpx.Client instead of AsyncClient.
    """
    platform = platform.lower().strip()
    if platform not in COMMENT_ACTOR_IDS or not video_urls or not APIFY_TOKEN:
        return []

    actor_id  = COMMENT_ACTOR_IDS[platform]
    normalize = _COMMENT_NORMALIZERS.get(platform)
    if normalize is None:
        return []

    if platform == "tiktok":
        run_input = {"postURLs": video_urls[:8], "maxComments": max_per_video}
    else:
        run_input = {"directUrls": video_urls[:8], "resultsLimit": max_per_video * len(video_urls[:8])}

    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    try:
        with httpx.Client(timeout=240.0) as client:
            response = client.post(url, json=run_input, params={"token": APIFY_TOKEN})
        if response.status_code not in (200, 201):
            return []
        raw = response.json()
        if not isinstance(raw, list):
            return []
        items = [r for r in raw if isinstance(r, dict) and "error" not in r]
        return [normalize(item) for item in items if item.get("text") or item.get("comment")]
    except Exception as e:
        print(f"[CommentSync] Failed: {e}")
        return []


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
