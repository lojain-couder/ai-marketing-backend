"""
Sales Metrics Extractor — bridges raw sales rows to MetricSnapshot.

Derives business KPIs (revenue, leads, conversion rate, retention)
from normalized sales data and social engagement signals so that
BusinessAdvisorEngine can produce sales-backed recommendations.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from .domain import MetricSnapshot


# ── Public API ────────────────────────────────────────────────────────────────

def extract_metric_snapshot(
    sales_rows: list[dict[str, Any]],
    social_rows: list[dict[str, Any]],
    notes: list[str] | None = None,
) -> MetricSnapshot:
    """Convert raw sales + social rows into a MetricSnapshot for the BI engine."""
    revenue = round(sum(float(r.get("revenue") or 0) for r in sales_rows), 2)

    unique_customers = len({r.get("customer_id") for r in sales_rows if r.get("customer_id")})
    leads = unique_customers if unique_customers > 0 else len(sales_rows)

    total_views = sum(int(r.get("views") or 0) for r in social_rows)
    conversion_rate = round(leads / total_views, 6) if total_views > 0 else 0.0

    total_customers = len(sales_rows)
    returning_keywords = {"returning", "repeat", "existing", "loyal", "عائد", "متكرر"}
    returning = sum(
        1 for r in sales_rows
        if any(kw in (r.get("customer_type") or "").lower() for kw in returning_keywords)
    )
    returning_rate = round(returning / total_customers, 4) if total_customers > 0 else 0.0

    engagement_rates = [float(r.get("engagement_rate") or 0) for r in social_rows]
    content_engagement = round(mean(engagement_rates), 4) if engagement_rates else 0.0

    ad_spend = round(sum(float(r.get("ad_spend") or 0) for r in sales_rows), 2)

    return MetricSnapshot(
        captured_at=datetime.now(timezone.utc),
        revenue=revenue,
        leads=leads,
        conversion_rate=conversion_rate,
        ad_spend=ad_spend,
        content_engagement_rate=content_engagement,
        returning_customer_rate=returning_rate,
        notes=notes or [],
    )


def build_sales_kpis(
    sales_rows: list[dict[str, Any]],
    social_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Human-readable KPI summary for the analysis output."""
    snapshot = extract_metric_snapshot(sales_rows, social_rows)
    total_orders = len(sales_rows)
    avg_order_value = round(snapshot.revenue / total_orders, 2) if total_orders > 0 else 0.0
    roas = round(snapshot.revenue / snapshot.ad_spend, 2) if snapshot.ad_spend > 0 else None

    top_products = _top_products(sales_rows)
    channel_breakdown = _channel_breakdown(sales_rows)

    return {
        "revenue": snapshot.revenue,
        "total_orders": total_orders,
        "unique_customers": snapshot.leads,
        "avg_order_value": avg_order_value,
        "conversion_rate": snapshot.conversion_rate,
        "returning_customer_rate": snapshot.returning_customer_rate,
        "ad_spend": snapshot.ad_spend,
        "roas": roas,
        "content_engagement_rate": snapshot.content_engagement_rate,
        "top_products": top_products,
        "channel_breakdown": channel_breakdown,
    }


def revenue_by_content_segment(
    social_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    For each media_type, topic, and platform, compute total and average revenue
    in the 7-day window following each post.  Used to find which content
    attributes correlate most strongly with downstream sales.
    """
    if not sales_rows:
        return {"available": False, "reason": "no_sales_data"}

    daily_revenue = _build_daily_revenue(sales_rows)

    media_revenue: dict[str, list[float]] = defaultdict(list)
    topic_revenue: dict[str, list[float]] = defaultdict(list)
    platform_revenue: dict[str, list[float]] = defaultdict(list)
    hook_revenue: dict[str, list[float]] = defaultdict(list)

    for row in social_rows:
        posted_at = _parse_iso(row.get("posted_at"))
        if posted_at is None:
            continue
        rev_7d = _revenue_in_window(daily_revenue, posted_at.date(), 7)

        media_type = (row.get("media_type") or "unknown").lower()
        media_revenue[media_type].append(rev_7d)

        topic = row.get("topic")
        if topic:
            topic_revenue[str(topic).lower()].append(rev_7d)

        platform = (row.get("platform") or "unknown").lower()
        platform_revenue[platform].append(rev_7d)

        hook = row.get("hook_type")
        if hook:
            hook_revenue[str(hook).lower()].append(rev_7d)

    return {
        "available": True,
        "revenue_by_media_type": _rank_segment(media_revenue),
        "revenue_by_topic": _rank_segment(topic_revenue)[:5],
        "revenue_by_platform": _rank_segment(platform_revenue),
        "revenue_by_hook": _rank_segment(hook_revenue)[:5],
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_daily_revenue(sales_rows: list[dict[str, Any]]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for row in sales_rows:
        dt = _parse_iso(row.get("order_date"))
        if dt is None:
            continue
        daily[dt.date().isoformat()] += float(row.get("revenue") or 0)
    return dict(daily)


def _revenue_in_window(daily: dict[str, float], start_date: Any, days: int) -> float:
    total = 0.0
    for offset in range(days + 1):
        key = start_date.fromordinal(start_date.toordinal() + offset).isoformat()
        total += daily.get(key, 0.0)
    return total


def _rank_segment(stats: dict[str, list[float]]) -> list[dict[str, Any]]:
    ranked = []
    for label, values in stats.items():
        if not values:
            continue
        ranked.append({
            "label": label,
            "total_revenue_7d": round(sum(values), 2),
            "avg_revenue_7d": round(sum(values) / len(values), 2),
            "posts": len(values),
        })
    ranked.sort(key=lambda x: x["total_revenue_7d"], reverse=True)
    return ranked


def _top_products(sales_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    product_revenue: dict[str, float] = defaultdict(float)
    product_count: dict[str, int] = defaultdict(int)
    for row in sales_rows:
        name = row.get("product_name") or "غير محدد"
        product_revenue[name] += float(row.get("revenue") or 0)
        product_count[name] += 1
    ranked = [
        {"product": k, "revenue": round(v, 2), "orders": product_count[k]}
        for k, v in product_revenue.items()
    ]
    ranked.sort(key=lambda x: x["revenue"], reverse=True)
    return ranked[:5]


def _channel_breakdown(sales_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    channel_revenue: dict[str, float] = defaultdict(float)
    channel_orders: dict[str, int] = defaultdict(int)
    for row in sales_rows:
        ch = (
            row.get("channel")
            or row.get("platform")
            or row.get("source")
            or "غير محدد"
        )
        channel_revenue[ch] += float(row.get("revenue") or 0)
        channel_orders[ch] += 1
    ranked = [
        {"channel": k, "revenue": round(v, 2), "orders": channel_orders[k]}
        for k, v in channel_revenue.items()
    ]
    ranked.sort(key=lambda x: x["revenue"], reverse=True)
    return ranked


def _parse_iso(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
