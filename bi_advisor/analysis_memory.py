"""
Analysis Memory Store — persists aggregated analysis results per business.

Stores only metric summaries (no raw videos, no raw sales rows).
Each analysis run produces one SocialSnapshot that is appended to the
business's history file and used by TrendEngine on the next run.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MEMORY_ROOT = os.getenv("ANALYSIS_MEMORY_ROOT", "/tmp/mudar_analysis_memory")

ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


# ── Snapshot dataclass ────────────────────────────────────────────────────────

@dataclass
class SocialSnapshot:
    business_id: str
    analyzed_at: str                   # ISO datetime string
    period_label: str                  # e.g. "التحليل الأول — مايو 2025"
    analysis_number: int               # 1, 2, 3, ...

    # Social performance (aggregated)
    platforms: list[str] = field(default_factory=list)
    total_posts: int = 0
    total_views: int = 0
    avg_engagement_rate: float = 0.0
    best_platform: str | None = None
    best_content_type: str | None = None
    best_posting_time: str | None = None
    top_topics: list[str] = field(default_factory=list)
    top_hooks: list[str] = field(default_factory=list)
    top_hashtags: list[str] = field(default_factory=list)

    # Sales metrics (optional — only when sales_data was provided)
    revenue: float = 0.0
    total_orders: int = 0
    avg_order_value: float = 0.0
    conversion_rate: float = 0.0
    returning_customer_rate: float = 0.0

    # Strategies recommended in this run (for outcome tracking)
    recommended_strategies: list[str] = field(default_factory=list)


# ── Memory store ──────────────────────────────────────────────────────────────

class AnalysisMemoryStore:
    """JSON file-backed store of SocialSnapshots, partitioned by business_id."""

    def __init__(self, root: str | Path = _MEMORY_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_snapshots(self, business_id: str) -> list[SocialSnapshot]:
        path = self._path(business_id)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text())
            return [self._deserialize(r) for r in raw.get("snapshots", [])]
        except Exception:
            return []

    def save_snapshot(self, snapshot: SocialSnapshot) -> None:
        path = self._path(snapshot.business_id)
        snapshots = self.load_snapshots(snapshot.business_id)

        # Deduplicate: if same analysis_number already exists, replace it
        snapshots = [s for s in snapshots if s.analysis_number != snapshot.analysis_number]
        snapshots.append(snapshot)
        snapshots.sort(key=lambda s: s.analysis_number)

        payload = {"snapshots": [asdict(s) for s in snapshots]}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _path(self, business_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in business_id)
        return self.root / f"{safe_id}.json"

    @staticmethod
    def _deserialize(row: dict[str, Any]) -> SocialSnapshot:
        return SocialSnapshot(
            business_id=row["business_id"],
            analyzed_at=row["analyzed_at"],
            period_label=row["period_label"],
            analysis_number=row["analysis_number"],
            platforms=row.get("platforms", []),
            total_posts=row.get("total_posts", 0),
            total_views=row.get("total_views", 0),
            avg_engagement_rate=row.get("avg_engagement_rate", 0.0),
            best_platform=row.get("best_platform"),
            best_content_type=row.get("best_content_type"),
            best_posting_time=row.get("best_posting_time"),
            top_topics=row.get("top_topics", []),
            top_hooks=row.get("top_hooks", []),
            top_hashtags=row.get("top_hashtags", []),
            revenue=row.get("revenue", 0.0),
            total_orders=row.get("total_orders", 0),
            avg_order_value=row.get("avg_order_value", 0.0),
            conversion_rate=row.get("conversion_rate", 0.0),
            returning_customer_rate=row.get("returning_customer_rate", 0.0),
            recommended_strategies=row.get("recommended_strategies", []),
        )


# ── Snapshot builder ──────────────────────────────────────────────────────────

def build_snapshot(
    business_id: str,
    engine_output: dict[str, Any],
    previous_count: int,
) -> SocialSnapshot:
    """Extract a SocialSnapshot from the analysis pipeline output dict."""
    now = datetime.now(timezone.utc)
    analysis_number = previous_count + 1
    period_label = _period_label(now, analysis_number)

    dm = engine_output.get("dashboard_metrics", {})
    cp = engine_output.get("content_patterns", {})
    sa = engine_output.get("sales_analysis", {})
    kpis = sa.get("sales_kpis", {}) if sa.get("available") else {}

    strategies = engine_output.get("strategies", [])
    rec_keys = [s.get("strategy_key") or s.get("title", "") for s in strategies if isinstance(s, dict)]

    return SocialSnapshot(
        business_id=business_id,
        analyzed_at=now.isoformat(),
        period_label=period_label,
        analysis_number=analysis_number,
        platforms=dm.get("analyzed_platforms") or dm.get("selected_platforms") or [],
        total_posts=int(dm.get("total_posts") or 0),
        total_views=int(dm.get("total_views") or 0),
        avg_engagement_rate=float(dm.get("avg_engagement_rate") or 0.0),
        best_platform=dm.get("best_platform"),
        best_content_type=dm.get("top_content_type"),
        best_posting_time=dm.get("top_posting_time"),
        top_topics=_extract_labels(cp.get("repeated_topics", []))[:5],
        top_hooks=_extract_labels(cp.get("high_performing_hooks", []))[:5],
        top_hashtags=_extract_labels(cp.get("best_hashtags", []))[:5],
        revenue=float(kpis.get("revenue") or 0.0),
        total_orders=int(kpis.get("total_orders") or 0),
        avg_order_value=float(kpis.get("avg_order_value") or 0.0),
        conversion_rate=float(kpis.get("conversion_rate") or 0.0),
        returning_customer_rate=float(kpis.get("returning_customer_rate") or 0.0),
        recommended_strategies=rec_keys[:5],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_label(dt: datetime, n: int) -> str:
    ordinals = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع",
                5: "الخامس", 6: "السادس", 7: "السابع", 8: "الثامن"}
    label = ordinals.get(n, f"رقم {n}")
    month = ARABIC_MONTHS.get(dt.month, str(dt.month))
    return f"التحليل {label} — {month} {dt.year}"


def _extract_labels(items: list) -> list[str]:
    result = []
    for item in items:
        if isinstance(item, dict):
            label = item.get("label") or item.get("topic") or item.get("tag") or ""
        else:
            label = str(item)
        if label:
            result.append(label)
    return result
