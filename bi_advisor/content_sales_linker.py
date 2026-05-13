from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


WINDOWS = (0, 1, 3, 7)

_DAYS_AR = {0: "الإثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس",
            4: "الجمعة",  5: "السبت",   6: "الأحد"}

_DURATION_BUCKETS = [
    ("أقل من 15 ثانية", 0,   15),
    ("15-30 ثانية",     15,  30),
    ("30-60 ثانية",     30,  60),
    ("1-3 دقائق",       60,  180),
    ("أكثر من 3 دقائق", 180, 99999),
]


# ── Posting time heatmap ──────────────────────────────────────────────────────

def analyze_posting_time_impact(
    social_rows: list[dict[str, Any]],
    sales_rows:  list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build a day-of-week × hour-of-day heatmap correlating post time with
    engagement rate and 7-day revenue window.
    Returns the best posting slots and a ranked list.
    """
    if not social_rows:
        return {"available": False, "reason": "no_social_data"}

    daily_revenue = _build_daily_revenue(sales_rows)

    slots: dict[tuple[int, int], list[dict]] = defaultdict(list)

    for row in social_rows:
        posted_at = _parse_iso(row.get("posted_at"))
        if posted_at is None:
            continue
        day  = posted_at.weekday()   # 0=Monday … 6=Sunday
        hour = posted_at.hour
        eng  = float(row.get("engagement_rate") or 0)
        rev  = _revenue_in_window(daily_revenue, posted_at.date(), 7)
        slots[(day, hour)].append({"eng": eng, "rev": rev})

    if not slots:
        return {"available": False, "reason": "no_parseable_dates"}

    heatmap = []
    for (day, hour), entries in slots.items():
        engs = [e["eng"] for e in entries]
        revs = [e["rev"] for e in entries]
        heatmap.append({
            "day":           day,
            "day_ar":        _DAYS_AR[day],
            "hour":          hour,
            "time_label":    f"{hour:02d}:00",
            "post_count":    len(entries),
            "avg_engagement": round(mean(engs) * 100, 2),
            "avg_revenue_7d": round(mean(revs), 2),
        })

    heatmap.sort(key=lambda x: (x["avg_revenue_7d"], x["avg_engagement"]), reverse=True)

    best = heatmap[0] if heatmap else {}
    return {
        "available":   True,
        "heatmap":     heatmap,
        "best_day":    best.get("day_ar", ""),
        "best_hour":   best.get("time_label", ""),
        "best_slot":   f"{best.get('day_ar', '')} الساعة {best.get('time_label', '')}",
        "top_slots":   heatmap[:5],
        "summary_ar":  _time_summary_ar(best),
    }


def _time_summary_ar(best: dict) -> str:
    if not best:
        return "لا تتوفر بيانات كافية لتحديد أفضل وقت نشر."
    return (
        f"أفضل وقت للنشر: {best.get('day_ar', '')} الساعة {best.get('time_label', '')} — "
        f"متوسط تفاعل {best.get('avg_engagement', 0):.1f}٪ "
        f"وإيراد {best.get('avg_revenue_7d', 0):.0f} خلال 7 أيام."
    )


# ── Duration sweet spot ───────────────────────────────────────────────────────

def analyze_duration_impact(
    social_rows: list[dict[str, Any]],
    sales_rows:  list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Group videos by duration bucket and find which length drives the most
    engagement and revenue for this specific account.
    """
    rows_with_duration = [r for r in social_rows if int(r.get("duration") or 0) > 0]
    if not rows_with_duration:
        return {"available": False, "reason": "no_duration_data"}

    daily_revenue = _build_daily_revenue(sales_rows)
    buckets: dict[str, list[dict]] = defaultdict(list)

    for row in rows_with_duration:
        dur = int(row.get("duration") or 0)
        eng = float(row.get("engagement_rate") or 0)
        rev = 0.0
        posted_at = _parse_iso(row.get("posted_at"))
        if posted_at:
            rev = _revenue_in_window(daily_revenue, posted_at.date(), 7)

        for label, lo, hi in _DURATION_BUCKETS:
            if lo <= dur < hi:
                buckets[label].append({"eng": eng, "rev": rev, "dur": dur})
                break

    if not buckets:
        return {"available": False, "reason": "no_matching_buckets"}

    stats = []
    for label, entries in buckets.items():
        engs = [e["eng"] for e in entries]
        revs = [e["rev"] for e in entries]
        durs = [e["dur"] for e in entries]
        stats.append({
            "label":            label,
            "post_count":       len(entries),
            "avg_duration_sec": round(mean(durs), 0),
            "avg_engagement":   round(mean(engs) * 100, 2),
            "avg_revenue_7d":   round(mean(revs), 2),
        })

    stats.sort(key=lambda x: (x["avg_revenue_7d"], x["avg_engagement"]), reverse=True)
    best = stats[0]

    return {
        "available":    True,
        "duration_stats": stats,
        "best_bucket":  best["label"],
        "summary_ar":   _duration_summary_ar(best, stats),
    }


def _duration_summary_ar(best: dict, stats: list[dict]) -> str:
    worst = stats[-1] if len(stats) > 1 else None
    msg = (
        f"أفضل طول للفيديو في حسابك: {best['label']} — "
        f"تفاعل {best['avg_engagement']:.1f}٪ وإيراد {best['avg_revenue_7d']:.0f}."
    )
    if worst and worst["avg_engagement"] < best["avg_engagement"] * 0.6:
        msg += f" تجنّبي الفيديوهات من نوع {worst['label']} — أداؤها ضعيف لحسابك."
    return msg


# ── Content-type × Sales impact ───────────────────────────────────────────────

def analyze_content_type_impact(
    social_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Find which content_type values historically correlated with the highest
    revenue in the 7-day window after posting.
    Also factors in engagement rate and visual_type from Gemini Vision.
    """
    if not sales_rows:
        return {"available": False, "reason": "no_sales_data"}

    daily_revenue = _build_daily_revenue(sales_rows)
    total_revenue = sum(daily_revenue.values())
    if total_revenue == 0:
        return {"available": False, "reason": "zero_revenue"}

    # Group by content_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in social_rows:
        ct = row.get("content_type") or "unknown"
        by_type[ct].append(row)

    # Group by visual_type (from Gemini Vision)
    by_visual: dict[str, list[dict]] = defaultdict(list)
    for row in social_rows:
        vt = row.get("visual_type") or ""
        if vt:
            by_visual[vt].append(row)

    type_stats = _compute_type_stats(by_type, daily_revenue)
    visual_stats = _compute_type_stats(by_visual, daily_revenue)

    top_type = type_stats[0] if type_stats else None
    top_visual = visual_stats[0] if visual_stats else None

    # Find posts with CTA/price mentions that also had high post-revenue
    cta_impact = _analyze_cta_impact(social_rows, daily_revenue)

    return {
        "available": True,
        "content_type_impact": type_stats,
        "visual_type_impact": visual_stats,
        "cta_impact": cta_impact,
        "top_revenue_content_type": top_type["content_type"] if top_type else None,
        "top_revenue_visual_type": top_visual["content_type"] if top_visual else None,
        "summary_ar": _content_type_summary_ar(type_stats, top_type),
    }


def _compute_type_stats(
    grouped: dict[str, list[dict]],
    daily_revenue: dict[str, float],
) -> list[dict[str, Any]]:
    stats = []
    for label, rows in grouped.items():
        if not label:
            continue
        rev_7d_list, rev_1d_list, eng_list = [], [], []
        for row in rows:
            posted_at = _parse_iso(row.get("posted_at"))
            if posted_at is None:
                continue
            rev_7d_list.append(_revenue_in_window(daily_revenue, posted_at.date(), 7))
            rev_1d_list.append(_revenue_in_window(daily_revenue, posted_at.date(), 1))
            eng_list.append(float(row.get("engagement_rate") or 0))

        if not rev_7d_list:
            continue

        avg_rev_7d = mean(rev_7d_list)
        avg_rev_1d = mean(rev_1d_list)
        avg_eng = mean(eng_list) if eng_list else 0.0

        stats.append({
            "content_type": label,
            "post_count": len(rows),
            "avg_revenue_7d": round(avg_rev_7d, 2),
            "avg_revenue_1d": round(avg_rev_1d, 2),
            "avg_engagement": round(avg_eng, 4),
            "recommendation_ar": _type_recommendation_ar(label, avg_rev_7d, avg_eng),
        })

    stats.sort(key=lambda x: (x["avg_revenue_7d"], x["avg_engagement"]), reverse=True)
    for rank, s in enumerate(stats, 1):
        s["rank"] = rank
    return stats


def _analyze_cta_impact(
    social_rows: list[dict],
    daily_revenue: dict[str, float],
) -> dict[str, Any]:
    """Compare revenue windows for posts with vs without CTA/price mentions."""
    with_cta, without_cta = [], []
    with_price, without_price = [], []

    for row in social_rows:
        posted_at = _parse_iso(row.get("posted_at"))
        if posted_at is None:
            continue
        rev = _revenue_in_window(daily_revenue, posted_at.date(), 3)
        if row.get("has_cta"):
            with_cta.append(rev)
        else:
            without_cta.append(rev)
        if row.get("mentions_price"):
            with_price.append(rev)
        else:
            without_price.append(rev)

    def _avg(lst):
        return round(mean(lst), 2) if lst else 0.0

    cta_lift = round((_avg(with_cta) - _avg(without_cta)) / max(_avg(without_cta), 1) * 100, 1)
    price_lift = round((_avg(with_price) - _avg(without_price)) / max(_avg(without_price), 1) * 100, 1)

    return {
        "cta_avg_revenue_3d": _avg(with_cta),
        "no_cta_avg_revenue_3d": _avg(without_cta),
        "cta_lift_pct": cta_lift,
        "price_mention_avg_revenue_3d": _avg(with_price),
        "no_price_avg_revenue_3d": _avg(without_price),
        "price_lift_pct": price_lift,
        "summary_ar": _cta_summary_ar(cta_lift, price_lift),
    }


def _type_recommendation_ar(content_type: str, avg_rev: float, avg_eng: float) -> str:
    labels = {
        "product_review":  "مراجعات المنتج",
        "promotional":     "المحتوى الترويجي",
        "educational":     "المحتوى التعليمي",
        "tutorial":        "الشروحات العملية",
        "unboxing":        "فيديوهات الفتح",
        "lifestyle":       "محتوى اللايف ستايل",
        "entertainment":   "المحتوى الترفيهي",
        "behind_scenes":   "الكواليس",
        "trending":        "التريندات",
        "challenge":       "التحديات",
        "product_demo":    "عرض المنتج",
        "talking_head":    "الحديث المباشر",
    }
    ar_label = labels.get(content_type, content_type)
    if avg_rev > 0 and avg_eng > 0.05:
        return f"انشري {ar_label} بانتظام — يجلب تفاعلاً ومبيعات في نفس الوقت"
    if avg_rev > 0:
        return f"ركّزي على {ar_label} — يرتبط بارتفاع المبيعات حتى لو التفاعل متوسط"
    if avg_eng > 0.05:
        return f"{ar_label} يجلب تفاعلاً جيداً لكن الربط بالمبيعات محدود"
    return f"راجعي استراتيجية {ar_label} — الأداء الإجمالي يمكن تحسينه"


def _content_type_summary_ar(
    type_stats: list[dict],
    top_type: dict | None,
) -> str:
    if not type_stats or not top_type:
        return "لا تتوفر بيانات كافية لتحليل أثر نوع المحتوى على المبيعات."
    label = top_type["content_type"]
    rev   = top_type["avg_revenue_7d"]
    count = top_type["post_count"]
    return (
        f"نوع المحتوى الأعلى ارتباطاً بالمبيعات هو «{label}» "
        f"بمتوسط إيراد {rev:.0f} خلال 7 أيام بعد النشر، استناداً لـ {count} منشور."
    )


def _cta_summary_ar(cta_lift: float, price_lift: float) -> str:
    parts = []
    if cta_lift > 10:
        parts.append(f"المنشورات التي تحتوي دعوة للتواصل/الشراء ترتبط بإيراد أعلى بنسبة {cta_lift:.0f}٪")
    if price_lift > 10:
        parts.append(f"ذكر السعر أو العروض يرتبط بزيادة الإيراد بنسبة {price_lift:.0f}٪")
    if not parts:
        return "لا يوجد فرق واضح حتى الآن بين المنشورات ذات الـ CTA والأخرى."
    return " — ".join(parts) + "."


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
