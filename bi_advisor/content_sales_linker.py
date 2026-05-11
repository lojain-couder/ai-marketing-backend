from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


WINDOWS = (0, 1, 3, 7)


def analyze_content_sales_links(
    social_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not sales_rows:
        return {
            "sales_included": False,
            "summary": "لم يتم رفع بيانات مبيعات، لذلك يعتمد التحليل على أداء المحتوى فقط.",
            "limitations": ["لا يمكن تحليل أثر المحتوى على المبيعات بدون بيانات مبيعات."],
            "top_correlated_content": [],
            "platform_sales_signals": [],
            "correlation_windows": {},
            "content_revenue_segments": {"available": False},
            "attribution_notes": [
                "لا توجد بيانات كافية لربط المحتوى بالمبيعات في هذه المرحلة."
            ],
        }

    daily_revenue = _build_daily_revenue(sales_rows)
    linked_posts: list[dict[str, Any]] = []

    for row in social_rows:
        posted_at = _parse_iso(row.get("posted_at"))
        if posted_at is None:
            continue

        window_revenue = {}
        for window in WINDOWS:
            window_revenue[f"{window}d"] = round(
                _revenue_in_window(daily_revenue, posted_at.date(), window),
                2,
            )

        evidence = _collect_evidence(row, sales_rows)
        linked_posts.append(
            {
                "platform": row.get("platform"),
                "content_id": row.get("content_id"),
                "content_url": row.get("content_url"),
                "caption": row.get("caption"),
                "campaign_name": row.get("campaign_name"),
                "product_mentioned": row.get("product_mentioned"),
                "revenue_windows": window_revenue,
                "association_strength": evidence["strength"],
                "evidence": evidence["evidence"],
                "statement": evidence["statement"],
            }
        )

    linked_posts.sort(
        key=lambda item: (
            item["association_strength"],
            item["revenue_windows"].get("7d", 0.0),
            item["revenue_windows"].get("1d", 0.0),
        ),
        reverse=True,
    )

    platform_signals = _platform_sales_signals(social_rows, sales_rows)

    from .sales_metrics_extractor import revenue_by_content_segment
    content_revenue_segments = revenue_by_content_segment(social_rows, sales_rows)

    return {
        "sales_included": True,
        "summary": _sales_summary(linked_posts, sales_rows),
        "limitations": _sales_limitations(sales_rows),
        "top_correlated_content": linked_posts[:5],
        "platform_sales_signals": platform_signals,
        "content_revenue_segments": content_revenue_segments,
        "correlation_windows": {
            "same_day": "0d",
            "plus_1_day": "1d",
            "plus_3_days": "3d",
            "plus_7_days": "7d",
        },
        "attribution_notes": [
            "تم استخدام الارتباط الزمني كإشارة أولية فقط.",
            "يتم اعتبار الحملة أو المصدر أو المنصة دليلاً أقوى من الارتباط الزمني وحده.",
            "لا يتم الادعاء بوجود نسبة مباشرة للمبيعات إلا عند وجود تطابق واضح في الحملة أو المصدر أو البيانات المرجعية.",
        ],
    }


def _build_daily_revenue(sales_rows: list[dict[str, Any]]) -> dict[str, float]:
    daily = defaultdict(float)
    for row in sales_rows:
        order_date = _parse_iso(row.get("order_date"))
        if order_date is None:
            continue
        daily[order_date.date().isoformat()] += float(row.get("revenue") or 0.0)
    return dict(daily)


def _revenue_in_window(daily_revenue: dict[str, float], start_date, days: int) -> float:
    total = 0.0
    for offset in range(days + 1):
        key = start_date.fromordinal(start_date.toordinal() + offset).isoformat()
        total += daily_revenue.get(key, 0.0)
    return total


def _collect_evidence(row: dict[str, Any], sales_rows: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: list[str] = []
    strength = 0

    campaign_name = (row.get("campaign_name") or "").strip().lower()
    if campaign_name and any((sale.get("campaign_name") or "").strip().lower() == campaign_name for sale in sales_rows):
        evidence.append("يوجد تطابق مباشر في اسم الحملة.")
        strength += 3

    product_mentioned = (row.get("product_mentioned") or "").strip().lower()
    if product_mentioned and any(product_mentioned in ((sale.get("product_name") or "").strip().lower()) for sale in sales_rows):
        evidence.append("يظهر المنتج المذكور أيضاً داخل بيانات المبيعات.")
        strength += 1

    platform_name = (row.get("platform") or "").strip().lower()
    if any(
        platform_name == ((sale.get("platform") or "").strip().lower())
        or platform_name == ((sale.get("source") or "").strip().lower())
        or platform_name == ((sale.get("medium") or "").strip().lower())
        for sale in sales_rows
    ):
        evidence.append("توجد إشارة مطابقة في المنصة أو المصدر أو الوسيط.")
        strength += 2

    if not evidence:
        evidence.append("الربط الحالي يعتمد على التوقيت وأنماط المحتوى فقط.")

    if strength >= 4:
        statement = "توجد مؤشرات قوية نسبياً على ارتباط هذا المحتوى بالمبيعات، لكن ما زال يلزم الحذر قبل اعتبارها نسبة مباشرة."
    elif strength >= 2:
        statement = "يبدو أن هذا المحتوى مرتبط بالمبيعات بشكل محتمل بناءً على إشارات داعمة، وليس هناك دليل حاسم على النسبة المباشرة."
    else:
        statement = "يوجد ارتباط زمني أو وصفي فقط، ولا توجد بيانات كافية للجزم بنسبة مباشرة للمبيعات."

    return {
        "strength": strength,
        "evidence": evidence,
        "statement": statement,
    }


def _platform_sales_signals(
    social_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    platform_counts = defaultdict(int)
    for sale in sales_rows:
        platform_key = (
            sale.get("platform")
            or sale.get("source")
            or sale.get("medium")
            or "unknown"
        )
        platform_counts[str(platform_key).lower()] += 1

    signals = []
    for platform in sorted({row.get("platform") for row in social_rows if row.get("platform")}):
        matching_sales = platform_counts.get(platform, 0)
        signals.append(
            {
                "platform": platform,
                "matching_sales_rows": matching_sales,
                "statement": (
                    f"يبدو أن منصة {platform} مرتبطة بـ {matching_sales} صف مبيعات عبر حقول platform/source/medium."
                    if matching_sales
                    else f"لا توجد إشارة ربط مباشرة كافية حالياً بين {platform} وحقول المصدر في المبيعات."
                ),
            }
        )
    return signals


def _sales_summary(linked_posts: list[dict[str, Any]], sales_rows: list[dict[str, Any]]) -> str:
    if not linked_posts:
        return "تم رفع بيانات المبيعات، لكن لا توجد تواريخ أو إشارات كافية لبناء ربط واضح مع المحتوى."
    strongest = linked_posts[0]
    revenue_7d = strongest["revenue_windows"].get("7d", 0.0)
    return (
        f"تم تحليل {len(sales_rows)} صف مبيعات. أعلى محتوى مرتبط زمنياً ظهر خلال نافذة 7 أيام بقيمة "
        f"{revenue_7d:.2f}، مع استخدام لغة حذرة لأن الربط لا يعني نسبة مباشرة."
    )


def _sales_limitations(sales_rows: list[dict[str, Any]]) -> list[str]:
    limitations: list[str] = []
    if not any(row.get("campaign_name") for row in sales_rows):
        limitations.append("لا توجد أسماء حملات كافية لعمل ربط مباشر بين المحتوى والمبيعات.")
    if not any(row.get("platform") or row.get("source") or row.get("medium") for row in sales_rows):
        limitations.append("لا توجد حقول منصة أو مصدر أو وسيط كافية لدعم نسبة المبيعات لقناة محددة.")
    if not any(row.get("product_name") for row in sales_rows):
        limitations.append("لا توجد أسماء منتجات كافية لتحليل ربط المحتوى بالمنتجات.")
    return limitations


def _parse_iso(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
