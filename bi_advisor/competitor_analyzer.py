"""
Competitor Analyzer

Compares the user's account against 1-3 competitor accounts:
- Content type distribution
- Posting frequency and engagement benchmarks
- Top hooks and hashtags they use
- Gaps: what works for them that the account doesn't do
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any


def compare_accounts(
    account_rows: list[dict],
    competitors: list[dict],
) -> dict[str, Any]:
    """
    account_rows: social rows for the main account (already analyzed).
    competitors: list of {username, platform, posts: [normalized video dicts]}

    Returns a comparison dict surfacing gaps and opportunities.
    """
    if not competitors:
        return {"available": False, "reason": "no_competitor_data"}

    account_stats = _compute_account_stats(account_rows)
    competitor_stats = [
        {**_compute_account_stats(c["posts"]), "username": c["username"], "platform": c["platform"]}
        for c in competitors
        if c.get("posts")
    ]

    if not competitor_stats:
        return {"available": False, "reason": "competitor_posts_empty"}

    gaps = _find_gaps(account_stats, competitor_stats)
    benchmark = _build_benchmark(account_stats, competitor_stats)
    top_competitor_hashtags = _top_competitor_hashtags(competitors)
    account_hashtags = set(account_stats["top_hashtags"])
    unused_hashtags = [h for h in top_competitor_hashtags if h not in account_hashtags][:10]

    return {
        "available": True,
        "account_stats": account_stats,
        "competitor_stats": competitor_stats,
        "benchmark": benchmark,
        "gaps": gaps,
        "unused_competitor_hashtags": unused_hashtags,
    }


def _compute_account_stats(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {
            "post_count": 0,
            "avg_engagement": 0.0,
            "avg_views": 0,
            "content_type_dist": {},
            "hook_type_dist": {},
            "top_hashtags": [],
            "posting_days": {},
        }

    engagements = [float(r.get("engagement_rate") or 0) for r in rows]
    views = [int(r.get("views") or 0) for r in rows]

    ct_counter: Counter = Counter()
    hook_counter: Counter = Counter()
    hashtag_counter: Counter = Counter()
    day_counter: Counter = Counter()

    for r in rows:
        ct = r.get("content_type") or r.get("_type") or "unknown"
        ct_counter[ct] += 1

        ht = r.get("hook_type") or ""
        if ht:
            hook_counter[ht] += 1

        for tag in re.findall(r"#\w+", str(r.get("caption") or "")):
            hashtag_counter[tag.lower()] += 1

        posted = str(r.get("posted_at") or "")
        if posted:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                day_counter[dt.strftime("%A")] += 1
            except ValueError:
                pass

    total = len(rows)
    return {
        "post_count": total,
        "avg_engagement": round(mean(engagements), 4) if engagements else 0.0,
        "avg_views": int(mean(views)) if views else 0,
        "content_type_dist": {k: round(v / total * 100, 1) for k, v in ct_counter.most_common(6)},
        "hook_type_dist": {k: round(v / total * 100, 1) for k, v in hook_counter.most_common(4)},
        "top_hashtags": [h for h, _ in hashtag_counter.most_common(10)],
        "posting_days": dict(day_counter.most_common(3)),
    }


def _find_gaps(
    account_stats: dict,
    competitor_stats: list[dict],
) -> list[dict[str, Any]]:
    gaps = []

    # Engagement gap
    comp_eng_avg = mean([c["avg_engagement"] for c in competitor_stats]) if competitor_stats else 0
    account_eng = account_stats["avg_engagement"]
    if comp_eng_avg > account_eng * 1.2:
        diff_pct = round((comp_eng_avg - account_eng) / max(account_eng, 0.0001) * 100, 0)
        gaps.append({
            "type": "engagement",
            "description": f"متوسط تفاعل المنافسين أعلى منك بـ {diff_pct:.0f}٪",
            "account_value": account_eng,
            "competitor_avg": round(comp_eng_avg, 4),
            "action": "راجع نوع المحتوى والـ hook المستخدم",
        })

    # Content type gaps — types competitors use heavily but account uses rarely
    all_comp_types: Counter = Counter()
    for c in competitor_stats:
        for ct, pct in c["content_type_dist"].items():
            all_comp_types[ct] += pct

    for ct, total_pct in all_comp_types.most_common(5):
        account_pct = account_stats["content_type_dist"].get(ct, 0)
        avg_comp_pct = total_pct / len(competitor_stats)
        if avg_comp_pct > account_pct + 15:
            gaps.append({
                "type": "content_type",
                "description": f"المنافسون يستخدمون «{ct}» بنسبة {avg_comp_pct:.0f}٪ مقارنة بـ {account_pct:.0f}٪ عندك",
                "content_type": ct,
                "your_pct": account_pct,
                "competitor_avg_pct": round(avg_comp_pct, 1),
                "action": f"جربي المزيد من محتوى {ct}",
            })

    # Hook type gaps
    all_comp_hooks: Counter = Counter()
    for c in competitor_stats:
        for ht, pct in c["hook_type_dist"].items():
            all_comp_hooks[ht] += pct

    for ht, total_pct in all_comp_hooks.most_common(3):
        account_pct = account_stats["hook_type_dist"].get(ht, 0)
        avg_comp_pct = total_pct / len(competitor_stats)
        if avg_comp_pct > account_pct + 20:
            gaps.append({
                "type": "hook_type",
                "description": f"المنافسون يستخدمون hook نوع «{ht}» أكثر منك بكثير",
                "hook_type": ht,
                "action": f"جربي بداية الفيديو بـ {ht}",
            })

    return gaps


def _build_benchmark(
    account_stats: dict,
    competitor_stats: list[dict],
) -> dict[str, Any]:
    avg_comp_eng = mean([c["avg_engagement"] for c in competitor_stats])
    avg_comp_views = int(mean([c["avg_views"] for c in competitor_stats]))
    best_competitor = max(competitor_stats, key=lambda c: c["avg_engagement"])

    return {
        "your_avg_engagement": account_stats["avg_engagement"],
        "competitor_avg_engagement": round(avg_comp_eng, 4),
        "your_avg_views": account_stats["avg_views"],
        "competitor_avg_views": avg_comp_views,
        "best_competitor_username": best_competitor["username"],
        "best_competitor_engagement": best_competitor["avg_engagement"],
        "you_vs_best_pct": round(
            (account_stats["avg_engagement"] - best_competitor["avg_engagement"])
            / max(best_competitor["avg_engagement"], 0.0001) * 100,
            1,
        ),
    }


def _top_competitor_hashtags(competitors: list[dict]) -> list[str]:
    counter: Counter = Counter()
    for c in competitors:
        for post in c.get("posts", []):
            for tag in re.findall(r"#\w+", str(post.get("caption") or "")):
                counter[tag.lower()] += 1
    return [h for h, _ in counter.most_common(20)]
