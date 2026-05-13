"""
Hook Performance Scorer

Ranks hook types by actual account performance:
- Engagement rate when using each hook type
- Revenue in 7-day window after posts with each hook type
- Recommends the best hook type to use for new content
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


def score_hook_types(
    social_rows: list[dict],
    sales_rows: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Returns hook types ranked by engagement + optional revenue correlation.
    Each entry includes avg engagement, avg views, post count, and a recommendation.
    """
    if not social_rows:
        return {"available": False, "reason": "no_social_data"}

    rows_with_hooks = [r for r in social_rows if r.get("hook_type")]
    if not rows_with_hooks:
        return {"available": False, "reason": "no_hook_data"}

    daily_revenue = _build_daily_revenue(sales_rows or [])

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows_with_hooks:
        grouped[row["hook_type"]].append(row)

    scored = []
    for hook_type, rows in grouped.items():
        engagements = [float(r.get("engagement_rate") or 0) for r in rows]
        views = [int(r.get("views") or 0) for r in rows]

        rev_7d_list = []
        if daily_revenue:
            for row in rows:
                dt = _parse_date(row.get("posted_at"))
                if dt:
                    rev_7d_list.append(_revenue_in_window(daily_revenue, dt.date(), 7))

        avg_eng   = mean(engagements)
        avg_views = int(mean(views))
        avg_rev   = mean(rev_7d_list) if rev_7d_list else None

        scored.append({
            "hook_type":      hook_type,
            "post_count":     len(rows),
            "avg_engagement": round(avg_eng, 4),
            "avg_views":      avg_views,
            "avg_revenue_7d": round(avg_rev, 2) if avg_rev is not None else None,
            "recommendation_ar": _hook_recommendation_ar(hook_type, avg_eng, avg_rev),
        })

    # Sort: primarily by revenue (if available), then by engagement
    has_revenue = any(s["avg_revenue_7d"] is not None for s in scored)
    if has_revenue:
        scored.sort(key=lambda x: (x["avg_revenue_7d"] or 0, x["avg_engagement"]), reverse=True)
    else:
        scored.sort(key=lambda x: x["avg_engagement"], reverse=True)

    for rank, s in enumerate(scored, 1):
        s["rank"] = rank

    best = scored[0] if scored else None

    return {
        "available": True,
        "ranked_hooks": scored,
        "best_hook_type": best["hook_type"] if best else None,
        "best_hook_reason_ar": best["recommendation_ar"] if best else "",
        "summary_ar": _summary_ar(scored),
    }


# ── Arabic labels & recommendations ──────────────────────────────────────────

_HOOK_LABELS_AR = {
    "question":  "السؤال",
    "story":     "القصة",
    "shock":     "الصدمة / المفاجأة",
    "tip":       "النصيحة",
    "product":   "عرض المنتج",
    "trend":     "التريند",
}


def _hook_recommendation_ar(hook_type: str, avg_eng: float, avg_rev: float | None) -> str:
    label = _HOOK_LABELS_AR.get(hook_type, hook_type)
    if avg_rev is not None and avg_rev > 0 and avg_eng > 0.04:
        return f"hook «{label}» يجلب تفاعلاً ومبيعات — استخدميه في المنتجات عالية القيمة"
    if avg_rev is not None and avg_rev > 0:
        return f"hook «{label}» مرتبط بارتفاع المبيعات حتى مع تفاعل متوسط"
    if avg_eng > 0.06:
        return f"hook «{label}» يجلب أعلى تفاعل لكن ارتباطه بالمبيعات غير مؤكد بعد"
    return f"hook «{label}» أداؤه متوسط — يمكن تحسينه بتجربة أساليب مختلفة"


def _summary_ar(scored: list[dict]) -> str:
    if not scored:
        return "لا توجد بيانات كافية لتقييم الـ hooks."
    best = scored[0]
    label = _HOOK_LABELS_AR.get(best["hook_type"], best["hook_type"])
    return (
        f"أفضل hook هو «{label}» بمتوسط تفاعل {best['avg_engagement']:.4f} "
        f"استناداً لـ {best['post_count']} منشور — ابدئي به فيديوهاتك القادمة."
    )


# ── Revenue helpers ───────────────────────────────────────────────────────────

def _build_daily_revenue(sales_rows: list[dict]) -> dict[str, float]:
    from collections import defaultdict
    daily: dict[str, float] = defaultdict(float)
    for row in sales_rows:
        dt = _parse_date(row.get("order_date"))
        if dt:
            daily[dt.date().isoformat()] += float(row.get("revenue") or 0)
    return dict(daily)


def _revenue_in_window(daily: dict, start_date: Any, days: int) -> float:
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
