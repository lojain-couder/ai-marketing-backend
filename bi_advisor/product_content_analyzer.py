"""
Product Content Analyzer

Bridges the sales product catalog with social media content:
- Extracts the product list from sales rows
- Matches each video to the product(s) it likely features (text + transcript)
- Computes per-product performance: engagement when featured, revenue proximity
- Provides structured data for Gemini to generate per-product strategy
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


# ── Public API ────────────────────────────────────────────────────────────────

def extract_product_list(sales_rows: list[dict]) -> list[dict]:
    """
    Return unique products from sales data, each with revenue + order stats.
    Result is sorted by revenue descending.
    """
    if not sales_rows:
        return []

    product_rev: dict[str, float] = defaultdict(float)
    product_orders: dict[str, int] = defaultdict(int)
    product_qty: dict[str, float] = defaultdict(float)

    for row in sales_rows:
        name = (row.get("product_name") or "").strip()
        if not name or name.lower() in ("غير محدد", "unknown", ""):
            continue
        product_rev[name] += float(row.get("revenue") or 0)
        product_orders[name] += 1
        product_qty[name] += float(row.get("quantity") or 1)

    products = [
        {
            "name": name,
            "revenue": round(product_rev[name], 2),
            "orders": product_orders[name],
            "total_qty": round(product_qty[name], 1),
            "avg_order_value": round(product_rev[name] / product_orders[name], 2)
            if product_orders[name] > 0 else 0.0,
        }
        for name in product_rev
    ]
    products.sort(key=lambda p: p["revenue"], reverse=True)
    return products


def match_videos_to_products(
    videos: list[dict],
    products: list[dict],
) -> list[dict]:
    """
    For each video, check caption + transcript + scene for product name mentions.
    Adds 'featured_products' list to each video dict.
    """
    if not products:
        return videos

    product_names = [p["name"] for p in products]

    for v in videos:
        text = " ".join(filter(None, [
            str(v.get("caption") or ""),
            str(v.get("transcript") or ""),
            str(v.get("spoken_topic") or ""),
            str(v.get("scene") or ""),
            str(v.get("topic") or ""),
        ])).lower()

        matched = []
        for name in product_names:
            # Match if product name (or significant words from it) appear in the text
            if _name_matches(name, text):
                matched.append(name)

        v["featured_products"] = matched

    return videos


def compute_product_video_stats(
    social_rows: list[dict],
    sales_rows: list[dict],
    products: list[dict],
) -> list[dict]:
    """
    For each product, compute:
    - How many videos feature it
    - Average engagement when it's featured vs account average
    - Average revenue in 7-day window after videos that feature it
    - Revenue from sales data
    """
    if not products:
        return []

    daily_revenue = _build_daily_revenue(sales_rows)
    overall_avg_eng = (
        mean([float(r.get("engagement_rate") or 0) for r in social_rows])
        if social_rows else 0.0
    )

    product_lookup = {p["name"]: p for p in products}
    result = []

    for product in products:
        name = product["name"]

        featuring_rows = [
            r for r in social_rows
            if name in (r.get("featured_products") or [])
        ]

        featuring_eng = (
            mean([float(r.get("engagement_rate") or 0) for r in featuring_rows])
            if featuring_rows else 0.0
        )

        # Revenue in windows after featuring videos
        rev_windows = []
        for row in featuring_rows:
            posted_at = _parse_date(row.get("posted_at"))
            if posted_at:
                rev = _revenue_in_window(daily_revenue, posted_at.date(), 7)
                rev_windows.append(rev)

        avg_rev_7d = mean(rev_windows) if rev_windows else 0.0

        # Engagement lift vs account average
        eng_lift_pct = (
            round((featuring_eng - overall_avg_eng) / overall_avg_eng * 100, 1)
            if overall_avg_eng > 0 and featuring_rows else None
        )

        result.append({
            "product_name": name,
            "revenue": product["revenue"],
            "orders": product["orders"],
            "avg_order_value": product["avg_order_value"],
            "featuring_video_count": len(featuring_rows),
            "avg_engagement_when_featured": round(featuring_eng, 4),
            "account_avg_engagement": round(overall_avg_eng, 4),
            "engagement_lift_pct": eng_lift_pct,
            "avg_revenue_7d_after_post": round(avg_rev_7d, 2),
            "featured_video_urls": [r.get("content_url") or r.get("url") for r in featuring_rows[:3]],
            "featured_captions": [(r.get("caption") or "")[:120] for r in featuring_rows[:3]],
            "has_content": len(featuring_rows) > 0,
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return result


def build_product_comment_map(
    videos: list[dict],
    raw_comments_by_url: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """
    Map product name → list of comment texts from videos that feature the product.
    raw_comments_by_url: {video_url: [comment_dicts]}
    """
    product_comments: dict[str, list[dict]] = defaultdict(list)

    for v in videos:
        url = v.get("url") or v.get("content_url") or ""
        featured = v.get("featured_products") or []
        comments = raw_comments_by_url.get(url, [])
        for product in featured:
            product_comments[product].extend(comments)

    return dict(product_comments)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _name_matches(product_name: str, text: str) -> bool:
    """
    Check if the product name (or key tokens) appears in the text.
    Handles Arabic and English product names.
    """
    name_lower = product_name.lower().strip()
    if not name_lower:
        return False

    # Direct substring match
    if name_lower in text:
        return True

    # Token match: all significant words (len > 2) must appear
    tokens = [t for t in re.split(r"[\s،,\-_/]+", name_lower) if len(t) > 2]
    if len(tokens) >= 2:
        return all(t in text for t in tokens)

    # Single meaningful token match
    if tokens:
        return tokens[0] in text

    return False


def _build_daily_revenue(sales_rows: list[dict]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for row in sales_rows:
        dt = _parse_date(row.get("order_date"))
        if dt:
            daily[dt.date().isoformat()] += float(row.get("revenue") or 0)
    return dict(daily)


def _revenue_in_window(daily: dict[str, float], start_date: Any, days: int) -> float:
    total = 0.0
    for offset in range(days + 1):
        key = start_date.fromordinal(start_date.toordinal() + offset).isoformat()
        total += daily.get(key, 0.0)
    return total


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
