"""
Caption Structure Analyzer — analyzes caption patterns vs engagement and revenue.

Analyzes: length buckets, opening type, emoji usage, CTA presence.
"""

from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


# Opening patterns
_QUESTION_STARTERS = (
    "?", "هل", "كيف", "ماذا", "ما ", "لماذا", "من ", "متى", "أين",
    "how", "what", "why", "when", "who", "which", "is ", "are ", "do ",
)
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA6F]"
)


def analyze_caption_structure(
    social_rows: list[dict],
    sales_rows:  list[dict] | None = None,
) -> dict:
    """
    Segment captions by structure and compute avg engagement + revenue per segment.
    """
    if not social_rows:
        return {"available": False, "reason": "no_social_data"}

    daily_revenue = _build_daily_revenue(sales_rows or [])

    # Accumulators
    length_data:  dict[str, list[dict]] = defaultdict(list)
    opening_data: dict[str, list[dict]] = defaultdict(list)
    cta_data:     dict[str, list[dict]] = defaultdict(list)
    emoji_data:   dict[str, list[dict]] = defaultdict(list)

    for row in social_rows:
        caption  = str(row.get("caption") or "")
        eng      = float(row.get("engagement_rate") or 0)
        rev      = _revenue_7d(daily_revenue, row.get("posted_at"))
        entry    = {"eng": eng, "rev": rev}

        # ── Length bucket ─────────────────────────────────────────────────────
        n = len(caption)
        if n < 50:
            length_data["قصير جداً (<50 حرف)"].append(entry)
        elif n < 150:
            length_data["قصير (50-150)"].append(entry)
        elif n < 300:
            length_data["متوسط (150-300)"].append(entry)
        else:
            length_data["طويل (>300)"].append(entry)

        # ── Opening type ──────────────────────────────────────────────────────
        stripped = caption.strip()
        if any(stripped.startswith(q) for q in _QUESTION_STARTERS):
            opening_data["سؤال"].append(entry)
        elif _EMOJI_RE.match(stripped):
            opening_data["إيموجي"].append(entry)
        elif re.match(r"^\d", stripped):
            opening_data["رقم (قائمة)"].append(entry)
        else:
            opening_data["نص عادي"].append(entry)

        # ── CTA presence ──────────────────────────────────────────────────────
        has_cta = bool(row.get("cta") or row.get("has_cta") or row.get("spoken_cta"))
        cta_data["مع CTA" if has_cta else "بدون CTA"].append(entry)

        # ── Emoji count ───────────────────────────────────────────────────────
        emoji_count = len(_EMOJI_RE.findall(caption))
        if emoji_count == 0:
            emoji_data["بدون إيموجي"].append(entry)
        elif emoji_count <= 3:
            emoji_data["1-3 إيموجي"].append(entry)
        else:
            emoji_data[">3 إيموجي"].append(entry)

    length_stats  = _summarize(length_data)
    opening_stats = _summarize(opening_data)
    cta_stats     = _summarize(cta_data)
    emoji_stats   = _summarize(emoji_data)

    best_length  = _best(length_stats,  "avg_engagement")
    best_opening = _best(opening_stats, "avg_engagement")
    best_emoji   = _best(emoji_stats,   "avg_engagement")

    return {
        "available":      True,
        "length_stats":   length_stats,
        "opening_stats":  opening_stats,
        "cta_stats":      cta_stats,
        "emoji_stats":    emoji_stats,
        "best_length":    best_length,
        "best_opening":   best_opening,
        "best_emoji":     best_emoji,
        "summary_ar":     _summary_ar(best_length, best_opening, cta_stats, best_emoji),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _summarize(groups: dict[str, list[dict]]) -> list[dict]:
    result = []
    for label, entries in groups.items():
        if not entries:
            continue
        engs = [e["eng"] for e in entries]
        revs = [e["rev"] for e in entries]
        result.append({
            "label":          label,
            "post_count":     len(entries),
            "avg_engagement": round(mean(engs) * 100, 2),
            "avg_revenue_7d": round(mean(revs), 2),
        })
    result.sort(key=lambda x: x["avg_engagement"], reverse=True)
    return result


def _best(stats: list[dict], key: str) -> str:
    return stats[0]["label"] if stats else ""


def _revenue_7d(daily: dict[str, float], posted_at: Any) -> float:
    if not daily or not posted_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(posted_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    total = 0.0
    for offset in range(8):
        key = dt.date().fromordinal(dt.date().toordinal() + offset).isoformat()
        total += daily.get(key, 0.0)
    return total


def _build_daily_revenue(sales_rows: list[dict]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for row in sales_rows:
        raw = row.get("order_date")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            daily[dt.date().isoformat()] += float(row.get("revenue") or 0)
        except ValueError:
            continue
    return dict(daily)


def _summary_ar(best_length: str, best_opening: str, cta_stats: list[dict], best_emoji: str) -> str:
    parts = []
    if best_length:
        parts.append(f"أفضل طول للكابشن: {best_length}")
    if best_opening:
        parts.append(f"أفضل افتتاحية: تبدأ بـ{best_opening}")
    if best_emoji:
        parts.append(f"أفضل استخدام للإيموجي: {best_emoji}")

    cta_with    = next((s for s in cta_stats if "مع" in s["label"]),    None)
    cta_without = next((s for s in cta_stats if "بدون" in s["label"]), None)
    if cta_with and cta_without:
        lift = round(cta_with["avg_engagement"] - cta_without["avg_engagement"], 1)
        if lift > 0:
            parts.append(f"الـ CTA يرفع التفاعل بـ {lift}+ نقطة مئوية")

    return " | ".join(parts) if parts else "لا تتوفر بيانات كافية لتحليل بنية الكابشن."
