from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any


SUPPORTED_SOCIAL_PLATFORMS = {"tiktok", "instagram", "x"}
MANUAL_ENRICHMENT_FIELDS = {
    "product_mentioned",
    "content_type",
    "hook_type",
    "topic",
    "cta",
    "target_audience",
    "campaign_name",
}


def normalize_social_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized in {"twitter", "x/twitter", "x / twitter"}:
        return "x"
    return normalized


def normalize_social_rows(
    platform: str,
    raw_data: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized_platform = normalize_social_platform(platform)
    warnings: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    if normalized_platform not in SUPPORTED_SOCIAL_PLATFORMS:
        return [], [f"Unsupported platform '{platform}'."]

    for index, row in enumerate(raw_data):
        if not isinstance(row, dict):
            warnings.append(
                f"Skipped row {index + 1} for {normalized_platform} because it is not an object."
            )
            continue

        normalized = _normalize_single_row(normalized_platform, row)
        if normalized is None:
            warnings.append(
                f"Skipped row {index + 1} for {normalized_platform} because no usable content_id was found."
            )
            continue

        dedupe_key = (normalized["platform"], normalized["content_id"])
        if dedupe_key in seen_keys:
            warnings.append(
                f"Removed duplicate row for {normalized['platform']} content_id {normalized['content_id']}."
            )
            continue

        seen_keys.add(dedupe_key)
        normalized_rows.append(normalized)

    if not normalized_rows:
        warnings.append(f"No usable rows were found for {normalized_platform}.")

    return normalized_rows, warnings


def _normalize_single_row(platform: str, row: dict[str, Any]) -> dict[str, Any] | None:
    if platform == "tiktok":
        normalized = {
            "platform": "tiktok",
            "content_id": _string_or_none(row.get("id")),
            "content_url": _string_or_none(row.get("webVideoUrl")),
            "posted_at": _iso_datetime(row.get("createTimeISO")),
            "caption": _string_or_empty(row.get("text")),
            "hashtags": _normalize_hashtags(row.get("hashtags")),
            "views": _to_int(row.get("playCount")),
            "likes": _to_int(row.get("diggCount")),
            "comments": _to_int(row.get("commentCount")),
            "shares": _to_int(row.get("shareCount")),
            "saves": _to_int(row.get("collectCount")),
            "quotes": 0,
            "duration": _to_float(_nested_get(row, "videoMeta.duration")),
            "thumbnail_url": _string_or_none(_nested_get(row, "videoMeta.coverUrl")),
            "video_url": _string_or_none(row.get("webVideoUrl")),
            "author_username": _string_or_empty(_nested_get(row, "authorMeta.name")),
            "author_display_name": _string_or_none(_nested_get(row, "authorMeta.nickname")),
            "author_followers": None,
            "music_name": _string_or_none(_nested_get(row, "musicMeta.musicName")),
            "location_name": None,
            "language": None,
            "is_repost": False,
            "is_quote": False,
            "external_urls": [],
            "content_type": _string_or_none(row.get("content_type")),
            "media_type": "video",
            "product_mentioned": _string_or_none(row.get("product_mentioned")),
            "hook_type": _string_or_none(row.get("hook_type")),
            "topic": _string_or_none(row.get("topic")),
            "cta": _string_or_none(row.get("cta")),
            "target_audience": _string_or_none(row.get("target_audience")),
            "campaign_name": _string_or_none(row.get("campaign_name")),
        }
    elif platform == "instagram":
        normalized = {
            "platform": "instagram",
            "content_id": _string_or_none(row.get("id")),
            "content_url": _string_or_none(row.get("url")),
            "posted_at": _iso_datetime(row.get("timestamp")),
            "caption": _string_or_empty(row.get("caption")),
            "hashtags": _normalize_hashtags(row.get("hashtags")),
            "views": _to_int(
                row.get("videoViewCount")
                if row.get("videoViewCount") not in (None, "")
                else row.get("videoPlayCount")
            ),
            "likes": _to_int(row.get("likesCount")),
            "comments": _to_int(row.get("commentsCount")),
            "shares": 0,
            "saves": 0,
            "quotes": 0,
            "duration": None,
            "thumbnail_url": _string_or_none(row.get("displayUrl")),
            "video_url": _string_or_none(row.get("videoUrl")),
            "author_username": _string_or_empty(row.get("ownerUsername")),
            "author_display_name": _string_or_none(row.get("ownerFullName")),
            "author_followers": None,
            "music_name": None,
            "location_name": _string_or_none(row.get("locationName")),
            "language": None,
            "is_repost": False,
            "is_quote": False,
            "external_urls": [],
            "content_type": _string_or_none(row.get("content_type")),
            "media_type": _string_or_none(row.get("type")) or "unknown",
            "product_mentioned": _string_or_none(row.get("product_mentioned")),
            "hook_type": _string_or_none(row.get("hook_type")),
            "topic": _string_or_none(row.get("topic")),
            "cta": _string_or_none(row.get("cta")),
            "target_audience": _string_or_none(row.get("target_audience")),
            "campaign_name": _string_or_none(row.get("campaign_name")),
        }
    else:
        normalized = {
            "platform": "x",
            "content_id": _string_or_none(row.get("id")),
            "content_url": _string_or_none(row.get("url")),
            "posted_at": _iso_datetime(row.get("createdAt")),
            "caption": _string_or_empty(row.get("fullText")),
            "hashtags": _normalize_hashtags(_nested_get(row, "entities.hashtags")),
            "views": _to_int(row.get("viewCount")),
            "likes": _to_int(row.get("likeCount")),
            "comments": _to_int(row.get("replyCount")),
            "shares": _to_int(row.get("retweetCount")),
            "saves": 0,
            "quotes": _to_int(row.get("quoteCount")),
            "duration": None,
            "thumbnail_url": None,
            "video_url": None,
            "author_username": _string_or_empty(_nested_get(row, "author.userName")),
            "author_display_name": _string_or_none(_nested_get(row, "author.displayName")),
            "author_followers": _to_int(_nested_get(row, "author.followers")),
            "music_name": None,
            "location_name": None,
            "language": _string_or_none(row.get("lang")),
            "is_repost": bool(row.get("isRetweet")),
            "is_quote": bool(row.get("isQuote")),
            "external_urls": _normalize_urls(_nested_get(row, "entities.urls")),
            "content_type": _string_or_none(row.get("content_type")),
            "media_type": "text",
            "product_mentioned": _string_or_none(row.get("product_mentioned")),
            "hook_type": _string_or_none(row.get("hook_type")),
            "topic": _string_or_none(row.get("topic")),
            "cta": _string_or_none(row.get("cta")),
            "target_audience": _string_or_none(row.get("target_audience")),
            "campaign_name": _string_or_none(row.get("campaign_name")),
        }

    content_id = normalized.get("content_id")
    if not content_id:
        return None

    normalized["engagement_rate"] = _calculate_engagement_rate(normalized)
    _apply_caption_enrichment(normalized)
    _copy_manual_enrichment(row, normalized)
    return normalized


def _calculate_engagement_rate(row: dict[str, Any]) -> float:
    views = _to_float(row.get("views"))
    if views <= 0:
        return 0.0

    likes = _to_float(row.get("likes"))
    comments = _to_float(row.get("comments"))
    shares = _to_float(row.get("shares"))
    saves = _to_float(row.get("saves"))
    quotes = _to_float(row.get("quotes"))

    if row.get("platform") == "x":
        return round((likes + comments + shares + quotes) / views, 6)

    if row.get("platform") == "instagram" and _to_float(row.get("shares")) == 0 and _to_float(row.get("saves")) == 0:
        return round((likes + comments) / views, 6)

    return round((likes + comments + shares + saves) / views, 6)


def _apply_caption_enrichment(row: dict[str, Any]) -> None:
    caption = row.get("caption", "") or ""
    hashtags = row.get("hashtags", []) or []

    if not row.get("topic"):
        row["topic"] = _infer_topic(caption, hashtags)
    if not row.get("hook_type"):
        row["hook_type"] = _infer_hook_type(caption)
    if not row.get("cta"):
        row["cta"] = _infer_cta(caption)


def _infer_topic(caption: str, hashtags: list[str]) -> str | None:
    if hashtags:
        return hashtags[0].lstrip("#")

    tokens = [
        token.strip(".,!?()[]{}:;\"'").lower()
        for token in caption.split()
        if len(token.strip(".,!?()[]{}:;\"'")) >= 4
    ]
    if not tokens:
        return None
    return " ".join(tokens[:3])


def _infer_hook_type(caption: str) -> str | None:
    text = caption.strip()
    if not text:
        return None
    if "?" in text:
        return "question"
    lowered = text.lower()
    if any(word in lowered for word in ["how", "tips", "steps", "طريقة", "كيف"]):
        return "educational"
    if any(word in lowered for word in ["why", "because", "ليش", "لماذا"]):
        return "insight"
    return "statement"


def _infer_cta(caption: str) -> str | None:
    lowered = caption.lower()
    cta_markers = [
        "shop now",
        "learn more",
        "dm",
        "link in bio",
        "comment",
        "تابع",
        "اطلب",
        "اشترك",
        "راسلنا",
    ]
    for marker in cta_markers:
        if marker in lowered:
            return marker
    return None


def _copy_manual_enrichment(source: dict[str, Any], target: dict[str, Any]) -> None:
    for field in MANUAL_ENRICHMENT_FIELDS:
        if source.get(field) not in (None, ""):
            target[field] = source.get(field)


def _normalize_hashtags(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_parts = value.replace("\n", " ").split()
        return [part if part.startswith("#") else f"#{part}" for part in raw_parts if part.startswith("#") or part]
    if isinstance(value, Iterable):
        hashtags: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("tag") or item.get("text")
                if name:
                    hashtags.append(name if str(name).startswith("#") else f"#{name}")
            elif item not in (None, ""):
                text = str(item)
                hashtags.append(text if text.startswith("#") else f"#{text}")
        return hashtags
    return []


def _normalize_urls(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        urls: list[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("expanded_url") or item.get("url") or item.get("expandedUrl")
                if candidate:
                    urls.append(str(candidate))
            elif item not in (None, ""):
                urls.append(str(item))
        return urls
    return []


def _nested_get(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _to_int(value: Any) -> int:
    if value in (None, "", False):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value in (None, "", False):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _iso_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None

    raw = str(value).strip()
    candidates = [
        raw,
        raw.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue

    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a %b %d %H:%M:%S %z %Y",
    ):
        try:
            parsed = datetime.strptime(raw, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    return None


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _string_or_empty(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)
