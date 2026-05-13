"""
Funnel Gap Detector — identifies where the customer journey breaks down.

Stages: Views → Engagement (proxy for interest) → Orders
Diagnoses whether the problem is at the Hook, Conversion, or Scale stage.
"""

from __future__ import annotations
from statistics import mean


def detect_funnel_gap(
    social_rows: list[dict],
    sales_rows:  list[dict],
) -> dict:
    """
    Analyze funnel health and detect the weakest stage.

    Returns diagnosis with the gap stage and recommended action.
    """
    if not social_rows:
        return {"available": False, "reason": "no_social_data"}

    total_views  = sum(int(r.get("views") or 0) for r in social_rows)
    total_orders = len(sales_rows)

    if total_views == 0:
        return {"available": False, "reason": "zero_views"}

    # Engagement rate as proxy for "clicked / interested"
    eng_rates = [float(r.get("engagement_rate") or 0) for r in social_rows]
    avg_eng   = mean(eng_rates) if eng_rates else 0.0

    # Quality-weighted engagement (comments + shares weigh more than likes)
    quality_scores = [_quality_score(r) for r in social_rows]
    avg_quality    = mean(quality_scores) if quality_scores else 0.0

    estimated_interested = int(total_views * avg_eng)
    order_to_interest    = (
        round(total_orders / estimated_interested * 100, 2)
        if estimated_interested > 0 else 0.0
    )
    overall_conversion   = round(total_orders / total_views * 100, 4)

    # ── Diagnose gap stage ────────────────────────────────────────────────────
    if avg_eng < 0.02:
        stage      = "hook"
        gap_ar     = "المشاهدون لا يتفاعلون — الـ hook أو أول 3 ثوانٍ لا تجذبهم"
        action_ar  = "جرّبي hook من نوع سؤال أو صدمة، وتأكدي أن الـ thumbnail جذاب"
        severity   = "high"
    elif avg_eng < 0.05:
        stage      = "interest"
        gap_ar     = "التفاعل منخفض نسبياً — المحتوى لا يحفّز على التعليق أو المشاركة"
        action_ar  = "اطرحي أسئلة في الكابشن، وشجّعي على التعليق والمشاركة بشكل مباشر"
        severity   = "medium"
    elif order_to_interest < 2.0 and total_orders > 0:
        stage      = "conversion"
        gap_ar     = "التفاعل جيد لكن التحويل للمبيعات ضعيف — المشكلة في صفحة المنتج أو السعر أو الـ CTA"
        action_ar  = "أضيفي CTA واضح في الفيديو، وراجعي صفحة المنتج وسهولة الشراء"
        severity   = "medium"
    elif total_orders == 0:
        stage      = "conversion"
        gap_ar     = "لا توجد مبيعات مسجّلة — تأكدي من ربط بيانات المبيعات أو راجعي رابط الشراء"
        action_ar  = "تأكدي أن رابط المتجر في البايو واضح وأن صفحة المنتج شغّالة"
        severity   = "high"
    else:
        stage      = "scale"
        gap_ar     = "المسار صحي — التفاعل والتحويل جيدان، والمشكلة في حجم الوصول"
        action_ar  = "ضاعفي تكرار النشر أو استثمري في إعلانات لتضخيم المحتوى الناجح"
        severity   = "low"

    # Per-video funnel signals
    top_hooks     = _top_videos_by(social_rows, "engagement_rate", 3)
    low_converters = _low_converter_videos(social_rows, avg_eng)

    return {
        "available":              True,
        "total_views":            total_views,
        "avg_engagement_rate":    round(avg_eng * 100, 2),
        "avg_quality_score":      round(avg_quality, 4),
        "estimated_interested":   estimated_interested,
        "total_orders":           total_orders,
        "engagement_to_order_pct": order_to_interest,
        "overall_conversion_pct": overall_conversion,
        "gap_stage":              stage,
        "severity":               severity,
        "gap_diagnosis_ar":       gap_ar,
        "recommended_action_ar":  action_ar,
        "top_hook_videos":        top_hooks,
        "low_converter_videos":   low_converters[:3],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quality_score(row: dict) -> float:
    views    = int(row.get("views") or 0)
    if views == 0:
        return 0.0
    likes    = int(row.get("likes") or 0)
    comments = int(row.get("comments") or 0)
    shares   = int(row.get("shares") or 0)
    return (likes * 1 + comments * 3 + shares * 5) / views


def _top_videos_by(rows: list[dict], key: str, n: int) -> list[dict]:
    sorted_rows = sorted(rows, key=lambda r: float(r.get(key) or 0), reverse=True)
    return [
        {
            "url":            r.get("content_url") or r.get("url", ""),
            "caption":        (r.get("caption") or "")[:80],
            "engagement_rate": round(float(r.get("engagement_rate") or 0) * 100, 2),
        }
        for r in sorted_rows[:n]
    ]


def _low_converter_videos(rows: list[dict], avg_eng: float) -> list[dict]:
    """Videos with above-average views but below-average engagement — hook attracts but content disappoints."""
    avg_views = mean([int(r.get("views") or 0) for r in rows]) if rows else 0
    return [
        {
            "url":             r.get("content_url") or r.get("url", ""),
            "caption":         (r.get("caption") or "")[:80],
            "views":           int(r.get("views") or 0),
            "engagement_rate": round(float(r.get("engagement_rate") or 0) * 100, 2),
            "note_ar":         "مشاهدات عالية لكن تفاعل منخفض — راجعي المحتوى بعد الـ hook",
        }
        for r in rows
        if int(r.get("views") or 0) > avg_views and float(r.get("engagement_rate") or 0) < avg_eng * 0.7
    ]
