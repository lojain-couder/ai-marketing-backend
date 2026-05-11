"""
Saudi/Gulf seasonal occasions database.
Returns upcoming seasons within a configurable lookahead window.

Hijri dates shift ~11 days earlier each Gregorian year.
Stored as (month, day) ranges in Gregorian for 2025-2027.
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Any


# ── Occasion database ─────────────────────────────────────────────────────────
# Each entry: name, start, end, tips (content angles), urgency (days before = "hot")

_OCCASIONS: list[dict[str, Any]] = [
    # ── Fixed Gregorian ────────────────────────────────────────────────────────
    {
        "key": "national_day",
        "name": "اليوم الوطني السعودي",
        "emoji": "🇸🇦",
        "recurrence": "gregorian_fixed",
        "month": 9, "day": 23,
        "duration_days": 2,
        "hot_before": 14,
        "angles": [
            "فخر بالهوية السعودية ومناسبة للعروض الوطنية",
            "محتوى يربط المنتج بقيم الانتماء والوطن",
            "تخفيضات أو هدايا بمناسبة اليوم الوطني",
        ],
        "hashtags": ["#اليوم_الوطني", "#93", "#Saudi_National_Day"],
    },
    {
        "key": "foundation_day",
        "name": "يوم التأسيس السعودي",
        "emoji": "🏛️",
        "recurrence": "gregorian_fixed",
        "month": 2, "day": 22,
        "duration_days": 2,
        "hot_before": 10,
        "angles": [
            "الاحتفاء بتاريخ المملكة وإرثها",
            "ربط العلامة التجارية بعراقة الهوية السعودية",
            "عروض ومسابقات احتفالية",
        ],
        "hashtags": ["#يوم_التأسيس", "#Foundation_Day"],
    },
    {
        "key": "mothers_day",
        "name": "يوم الأم",
        "emoji": "🌹",
        "recurrence": "gregorian_fixed",
        "month": 3, "day": 21,
        "duration_days": 1,
        "hot_before": 10,
        "angles": [
            "هدايا مناسبة للأم — تسهيل قرار الشراء",
            "محتوى عاطفي يلمس قلب الجمهور",
            "عروض خاصة بيوم الأم",
        ],
        "hashtags": ["#يوم_الأم", "#Mothers_Day"],
    },
    {
        "key": "white_friday",
        "name": "الجمعة البيضاء (White Friday)",
        "emoji": "🛍️",
        "recurrence": "gregorian_fixed",
        "month": 11, "day": 29,
        "duration_days": 4,
        "hot_before": 14,
        "angles": [
            "أكبر تخفيضات السنة — عروض لا تُفوَّت",
            "بناء قائمة انتظار وإثارة الترقب",
            "محتوى عد تنازلي للعرض",
        ],
        "hashtags": ["#الجمعة_البيضاء", "#WhiteFriday", "#تخفيضات"],
    },
    {
        "key": "back_to_school",
        "name": "العودة للمدارس",
        "emoji": "📚",
        "recurrence": "gregorian_fixed",
        "month": 8, "day": 20,
        "duration_days": 14,
        "hot_before": 21,
        "angles": [
            "منتجات تلائم موسم الدراسة",
            "تحضيرات البداية الجديدة",
            "خصومات للطلاب والأسر",
        ],
        "hashtags": ["#العودة_للمدارس", "#back_to_school"],
    },
    {
        "key": "new_year",
        "name": "رأس السنة الميلادية",
        "emoji": "🎆",
        "recurrence": "gregorian_fixed",
        "month": 1, "day": 1,
        "duration_days": 2,
        "hot_before": 7,
        "angles": [
            "أهداف وعزائم العام الجديد",
            "عروض بداية العام",
        ],
        "hashtags": ["#سنة_جديدة", "#NewYear"],
    },
    # ── Hijri/Islamic — approximate Gregorian dates per year ──────────────────
    {
        "key": "ramadan_2025",
        "name": "رمضان الكريم",
        "emoji": "🌙",
        "recurrence": "one_time",
        "start": date(2025, 3, 1), "end": date(2025, 3, 30),
        "hot_before": 21,
        "angles": [
            "محتوى روحاني ومُلهم يناسب أجواء رمضان",
            "عروض إفطار وسحور وتجمعات عائلية",
            "محتوى ليلي يناسب سهرات رمضان",
            "خير وعطاء — ربط المنتج بقيم رمضان",
        ],
        "hashtags": ["#رمضان_كريم", "#Ramadan", "#رمضان"],
    },
    {
        "key": "ramadan_2026",
        "name": "رمضان الكريم",
        "emoji": "🌙",
        "recurrence": "one_time",
        "start": date(2026, 2, 18), "end": date(2026, 3, 19),
        "hot_before": 21,
        "angles": [
            "محتوى روحاني ومُلهم يناسب أجواء رمضان",
            "عروض إفطار وسحور وتجمعات عائلية",
            "محتوى ليلي يناسب سهرات رمضان",
            "خير وعطاء — ربط المنتج بقيم رمضان",
        ],
        "hashtags": ["#رمضان_كريم", "#Ramadan", "#رمضان"],
    },
    {
        "key": "eid_fitr_2025",
        "name": "عيد الفطر المبارك",
        "emoji": "🎉",
        "recurrence": "one_time",
        "start": date(2025, 3, 30), "end": date(2025, 4, 3),
        "hot_before": 14,
        "angles": [
            "تهنئة العيد — محتوى احتفالي بهيج",
            "هدايا العيد وعروض الملابس والعطور",
            "أجواء العيد وزيارة الأهل",
        ],
        "hashtags": ["#عيد_الفطر", "#عيدكم_مبارك", "#Eid"],
    },
    {
        "key": "eid_adha_2025",
        "name": "عيد الأضحى المبارك",
        "emoji": "🐑",
        "recurrence": "one_time",
        "start": date(2025, 6, 6), "end": date(2025, 6, 10),
        "hot_before": 14,
        "angles": [
            "روح التضحية والعطاء",
            "تجهيزات العيد الكبير",
            "عروض خاصة موسم الحج والعيد",
        ],
        "hashtags": ["#عيد_الأضحى", "#عيدكم_مبارك", "#EidAlAdha"],
    },
    {
        "key": "eid_fitr_2026",
        "name": "عيد الفطر المبارك",
        "emoji": "🎉",
        "recurrence": "one_time",
        "start": date(2026, 3, 20), "end": date(2026, 3, 23),
        "hot_before": 14,
        "angles": [
            "تهنئة العيد — محتوى احتفالي بهيج",
            "هدايا العيد وعروض الملابس والعطور",
            "أجواء العيد وزيارة الأهل",
        ],
        "hashtags": ["#عيد_الفطر", "#عيدكم_مبارك", "#Eid"],
    },
    {
        "key": "eid_adha_2026",
        "name": "عيد الأضحى المبارك",
        "emoji": "🐑",
        "recurrence": "one_time",
        "start": date(2026, 5, 26), "end": date(2026, 5, 30),
        "hot_before": 14,
        "angles": [
            "روح التضحية والعطاء",
            "تجهيزات العيد الكبير",
            "عروض خاصة موسم الحج والعيد",
        ],
        "hashtags": ["#عيد_الأضحى", "#عيدكم_مبارك", "#EidAlAdha"],
    },
]


# ── Public API ────────────────────────────────────────────────────────────────

def get_active_seasons(
    today: date | None = None,
    lookahead_days: int = 30,
) -> list[dict[str, Any]]:
    """
    Return occasions that are active now or starting within `lookahead_days`.
    Each result includes days_until (negative = already started) and urgency level.
    """
    if today is None:
        today = date.today()

    active = []
    for occ in _OCCASIONS:
        start, end = _resolve_dates(occ, today)
        if start is None:
            continue

        days_until = (start - today).days
        days_left  = (end - today).days

        # Already ended
        if days_left < 0:
            continue

        # Starts too far in the future
        if days_until > lookahead_days:
            continue

        in_progress = days_until <= 0 <= days_left
        urgency = (
            "active"   if in_progress else
            "hot"      if days_until <= 7 else
            "upcoming"
        )

        active.append({
            "key":        occ["key"],
            "name":       occ["name"],
            "emoji":      occ["emoji"],
            "start":      start.isoformat(),
            "end":        end.isoformat(),
            "days_until": days_until,
            "urgency":    urgency,
            "angles":     occ["angles"],
            "hashtags":   occ["hashtags"],
        })

    active.sort(key=lambda x: x["days_until"])
    return active


def seasons_context_text(today: date | None = None, lookahead_days: int = 30) -> str:
    """One-line summary string for LLM prompts."""
    seasons = get_active_seasons(today, lookahead_days)
    if not seasons:
        return ""
    parts = []
    for s in seasons:
        label = (
            f"{s['emoji']} {s['name']} (جارٍ الآن)" if s["urgency"] == "active"
            else f"{s['emoji']} {s['name']} (بعد {s['days_until']} يوم)"
        )
        parts.append(label)
    return "المواسم القادمة: " + " | ".join(parts)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_dates(occ: dict, today: date) -> tuple[date | None, date | None]:
    rec = occ.get("recurrence", "")

    if rec == "one_time":
        return occ["start"], occ["end"]

    if rec == "gregorian_fixed":
        month, day = occ["month"], occ["day"]
        duration = occ.get("duration_days", 1)
        for year in (today.year, today.year + 1):
            try:
                start = date(year, month, day)
                end   = start + timedelta(days=duration - 1)
                if end >= today:
                    return start, end
            except ValueError:
                continue

    return None, None
