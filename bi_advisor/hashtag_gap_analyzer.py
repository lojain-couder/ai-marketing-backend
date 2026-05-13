"""
Hashtag Gap Analyzer

Finds hashtags used by competitors (or trending in the niche)
that the account has never used — prioritized by competitor engagement signal.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


def find_hashtag_gaps(
    account_rows: list[dict],
    competitor_data: list[dict] | None,
    gemini_suggested: list[str] | None = None,
) -> dict[str, Any]:
    """
    account_rows:       social rows for the main account
    competitor_data:    list of {username, posts: [...]} from competitor scraping
    gemini_suggested:   hashtags Gemini suggests are trending in the niche

    Returns gaps (unused hashtags) ranked by signal strength.
    """
    account_hashtags = _extract_hashtags(
        [str(r.get("caption") or "") for r in account_rows]
    )

    competitor_hashtag_counts: Counter = Counter()
    if competitor_data:
        for comp in competitor_data:
            for post in comp.get("posts", []):
                for tag in _extract_hashtags([str(post.get("caption") or "")]):
                    competitor_hashtag_counts[tag] += 1

    gaps = []

    # Competitor hashtags not used by the account
    for tag, freq in competitor_hashtag_counts.most_common(30):
        if tag not in account_hashtags:
            gaps.append({
                "hashtag": tag,
                "source": "competitor",
                "competitor_usage_count": freq,
                "signal_strength": "high" if freq >= 3 else "medium",
            })

    # Gemini-suggested trending hashtags not used by the account
    if gemini_suggested:
        for tag in gemini_suggested:
            tag_norm = tag.lower().strip().lstrip("#")
            tag_with_hash = f"#{tag_norm}"
            if tag_with_hash not in account_hashtags and tag_norm not in account_hashtags:
                already = any(g["hashtag"].lstrip("#") == tag_norm for g in gaps)
                if not already:
                    gaps.append({
                        "hashtag": f"#{tag_norm}",
                        "source": "trending_suggested",
                        "competitor_usage_count": 0,
                        "signal_strength": "medium",
                    })

    # Sort: high signal first, then by competitor usage
    gaps.sort(key=lambda g: (0 if g["signal_strength"] == "high" else 1, -g["competitor_usage_count"]))

    top_gaps = gaps[:15]

    return {
        "available": bool(top_gaps),
        "account_hashtag_count": len(account_hashtags),
        "gap_count": len(top_gaps),
        "gaps": top_gaps,
        "summary_ar": _summary_ar(top_gaps, account_hashtags),
    }


def _extract_hashtags(texts: list[str]) -> set[str]:
    tags: set[str] = set()
    for text in texts:
        for tag in re.findall(r"#\w+", text):
            tags.add(tag.lower())
    return tags


def _summary_ar(gaps: list[dict], account_tags: set[str]) -> str:
    if not gaps:
        return "لا توجد هاشتاقات ذات قيمة مفقودة — حساباتك تغطي نفس الهاشتاقات."
    high = [g for g in gaps if g["signal_strength"] == "high"]
    comp_gaps = [g for g in gaps if g["source"] == "competitor"]
    parts = [f"وجدنا {len(gaps)} هاشتاق لم تستخدمه/يها بعد."]
    if high:
        parts.append(f"{len(high)} منها بإشارة قوية من المنافسين.")
    if comp_gaps:
        top3 = ", ".join(g["hashtag"] for g in comp_gaps[:3])
        parts.append(f"أبرزها: {top3}.")
    return " ".join(parts)
