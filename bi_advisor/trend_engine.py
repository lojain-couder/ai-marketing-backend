"""
Trend Engine — compares SocialSnapshots across time and produces:
  - metric deltas (engagement, views, revenue, conversion, retention)
  - Arabic insight sentences ready for display
  - strategy adjustment signals to improve future recommendations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .analysis_memory import SocialSnapshot


# ── Trend direction thresholds ────────────────────────────────────────────────
_STRONG = 10.0   # |delta| > 10% → strong signal
_WEAK   =  3.0   # |delta| >  3% → weak signal (else stable)


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class MetricTrend:
    metric_key: str
    label_ar: str           # "التفاعل"
    previous: float
    current: float
    delta_pct: float
    direction: str          # up_strong | up | stable | down | down_strong
    insight_ar: str         # ready-to-display Arabic sentence


@dataclass
class TrendReport:
    has_history: bool
    total_analyses: int
    previous_period: str    # label of the period being compared against
    current_period: str
    metric_trends: list[MetricTrend] = field(default_factory=list)

    # Summary
    improving: list[str] = field(default_factory=list)   # Arabic labels
    declining: list[str] = field(default_factory=list)
    stable: list[str] = field(default_factory=list)
    overall_direction: str = "baseline"  # improving|declining|stable|mixed|baseline

    # Pattern changes
    platform_shifted: bool = False
    content_type_changed: bool = False
    platform_shift_note: str = ""
    content_type_note: str = ""

    # Strategy-level feedback
    strategy_signals: list[dict[str, str]] = field(default_factory=list)

    # Top-level Arabic narratives (shown to the user)
    arabic_summary: str = ""
    arabic_insights: list[str] = field(default_factory=list)


# ── Main engine ───────────────────────────────────────────────────────────────

class TrendEngine:

    def analyze(self, snapshots: list[SocialSnapshot]) -> TrendReport:
        """
        Build a TrendReport from a history of SocialSnapshots.
        Requires at least 2 snapshots to produce comparisons.
        """
        if len(snapshots) < 2:
            latest = snapshots[-1] if snapshots else None
            return TrendReport(
                has_history=False,
                total_analyses=len(snapshots),
                previous_period="—",
                current_period=latest.period_label if latest else "—",
                arabic_summary="هذا أول تحليل — ستظهر مقارنات التحسن بعد التحليل القادم.",
            )

        prev = snapshots[-2]
        curr = snapshots[-1]

        metric_trends = self._build_metric_trends(prev, curr)
        improving = [t.label_ar for t in metric_trends if t.direction in ("up", "up_strong")]
        declining = [t.label_ar for t in metric_trends if t.direction in ("down", "down_strong")]
        stable    = [t.label_ar for t in metric_trends if t.direction == "stable"]

        overall = self._overall_direction(metric_trends)
        platform_shifted, platform_note = self._platform_change(prev, curr)
        content_changed, content_note = self._content_type_change(prev, curr)
        strategy_signals = self._strategy_signals(prev, curr, metric_trends)
        insights = self._build_insights(metric_trends, platform_note, content_note, snapshots)
        summary = self._build_summary(overall, improving, declining, prev, curr)

        return TrendReport(
            has_history=True,
            total_analyses=len(snapshots),
            previous_period=prev.period_label,
            current_period=curr.period_label,
            metric_trends=metric_trends,
            improving=improving,
            declining=declining,
            stable=stable,
            overall_direction=overall,
            platform_shifted=platform_shifted,
            content_type_changed=content_changed,
            platform_shift_note=platform_note,
            content_type_note=content_note,
            strategy_signals=strategy_signals,
            arabic_summary=summary,
            arabic_insights=insights,
        )

    # ── Metric trends ─────────────────────────────────────────────────────────

    def _build_metric_trends(
        self,
        prev: SocialSnapshot,
        curr: SocialSnapshot,
    ) -> list[MetricTrend]:
        metrics = [
            ("avg_engagement_rate", "نسبة التفاعل", prev.avg_engagement_rate, curr.avg_engagement_rate),
            ("total_views",         "المشاهدات",    float(prev.total_views),   float(curr.total_views)),
            ("total_posts",         "عدد المنشورات", float(prev.total_posts),  float(curr.total_posts)),
        ]
        if prev.revenue > 0 or curr.revenue > 0:
            metrics.append(("revenue", "الإيرادات", prev.revenue, curr.revenue))
        if prev.total_orders > 0 or curr.total_orders > 0:
            metrics.append(("total_orders", "الطلبات", float(prev.total_orders), float(curr.total_orders)))
        if prev.conversion_rate > 0 or curr.conversion_rate > 0:
            metrics.append(("conversion_rate", "معدل التحويل", prev.conversion_rate, curr.conversion_rate))
        if prev.returning_customer_rate > 0 or curr.returning_customer_rate > 0:
            metrics.append(("returning_customer_rate", "العملاء المتكررون",
                             prev.returning_customer_rate, curr.returning_customer_rate))

        trends = []
        for key, label, p_val, c_val in metrics:
            delta = _pct(p_val, c_val)
            direction = _direction(delta)
            trends.append(MetricTrend(
                metric_key=key,
                label_ar=label,
                previous=round(p_val, 4),
                current=round(c_val, 4),
                delta_pct=round(delta, 1),
                direction=direction,
                insight_ar=_metric_sentence(label, delta, direction, p_val, c_val, key),
            ))
        return trends

    # ── Pattern change detection ──────────────────────────────────────────────

    def _platform_change(self, prev: SocialSnapshot, curr: SocialSnapshot) -> tuple[bool, str]:
        if prev.best_platform and curr.best_platform and prev.best_platform != curr.best_platform:
            return True, (
                f"تغيّرت المنصة الأفضل أداءً من {prev.best_platform} إلى {curr.best_platform} — "
                f"راقبي هذا التحول في الخطة القادمة."
            )
        return False, ""

    def _content_type_change(self, prev: SocialSnapshot, curr: SocialSnapshot) -> tuple[bool, str]:
        if prev.best_content_type and curr.best_content_type and prev.best_content_type != curr.best_content_type:
            return True, (
                f"نوع المحتوى الأفضل تغيّر من ({prev.best_content_type}) إلى ({curr.best_content_type}) — "
                f"حوّلي ثقل الخطة نحو النوع الجديد."
            )
        return False, ""

    # ── Strategy outcome signals ──────────────────────────────────────────────

    def _strategy_signals(
        self,
        prev: SocialSnapshot,
        curr: SocialSnapshot,
        metric_trends: list[MetricTrend],
    ) -> list[dict[str, str]]:
        signals = []
        improving_keys = {t.metric_key for t in metric_trends if t.direction in ("up", "up_strong")}
        declining_keys  = {t.metric_key for t in metric_trends if t.direction in ("down", "down_strong")}

        for strategy in prev.recommended_strategies:
            key = strategy.lower()

            if "content" in key or "scale" in key:
                if "avg_engagement_rate" in improving_keys or "total_views" in improving_keys:
                    signals.append({
                        "strategy": strategy,
                        "outcome": "worked",
                        "signal_ar": f"استراتيجية المحتوى '{strategy}' ساهمت في رفع التفاعل والمشاهدات — استمر فيها.",
                    })
                elif "avg_engagement_rate" in declining_keys:
                    signals.append({
                        "strategy": strategy,
                        "outcome": "not_working",
                        "signal_ar": f"استراتيجية '{strategy}' لم تحسّن التفاعل — راجع نوع المحتوى أو توقيت النشر.",
                    })

            if "conversion" in key or "funnel" in key:
                if "conversion_rate" in improving_keys:
                    signals.append({
                        "strategy": strategy,
                        "outcome": "worked",
                        "signal_ar": f"استراتيجية التحويل '{strategy}' أثّرت إيجاباً — معدل التحويل ارتفع.",
                    })
                elif "conversion_rate" in declining_keys:
                    signals.append({
                        "strategy": strategy,
                        "outcome": "not_working",
                        "signal_ar": f"استراتيجية التحويل '{strategy}' لم تُصلح المشكلة — المشكلة قد تكون في العرض أو الصفحة.",
                    })

            if "retention" in key:
                if "returning_customer_rate" in improving_keys:
                    signals.append({
                        "strategy": strategy,
                        "outcome": "worked",
                        "signal_ar": f"استراتيجية الاحتفاظ '{strategy}' نجحت — نسبة العملاء المتكررين ارتفعت.",
                    })

        return signals

    # ── Arabic narrative builders ─────────────────────────────────────────────

    def _build_insights(
        self,
        metric_trends: list[MetricTrend],
        platform_note: str,
        content_note: str,
        snapshots: list[SocialSnapshot],
    ) -> list[str]:
        insights = [t.insight_ar for t in metric_trends if t.direction != "stable"]
        if platform_note:
            insights.append(platform_note)
        if content_note:
            insights.append(content_note)
        if len(snapshots) >= 3:
            long_term = self._long_term_note(snapshots)
            if long_term:
                insights.append(long_term)
        return insights

    def _long_term_note(self, snapshots: list[SocialSnapshot]) -> str:
        """Produce a note spanning 3+ analyses."""
        first = snapshots[0]
        latest = snapshots[-1]
        delta_eng = _pct(first.avg_engagement_rate, latest.avg_engagement_rate)
        delta_views = _pct(float(first.total_views), float(latest.total_views))
        n = len(snapshots)
        if delta_eng > 5:
            return (
                f"على مدى {n} تحليلات، التفاعل ارتفع إجمالاً بنسبة {delta_eng:.0f}% "
                f"مقارنة بـ {first.period_label} — النمط الحالي يسير بالاتجاه الصحيح."
            )
        if delta_eng < -5:
            return (
                f"على مدى {n} تحليلات، التفاعل انخفض إجمالاً بنسبة {abs(delta_eng):.0f}% "
                f"مقارنة بـ {first.period_label} — الخطة تحتاج مراجعة جذرية."
            )
        if delta_views > 10:
            return (
                f"المشاهدات الإجمالية ارتفعت {delta_views:.0f}% مقارنة بـ {first.period_label} "
                f"رغم استقرار التفاعل — الوصول يكبر لكن التحويل يحتاج تحسيناً."
            )
        return ""

    def _build_summary(
        self,
        overall: str,
        improving: list[str],
        declining: list[str],
        prev: SocialSnapshot,
        curr: SocialSnapshot,
    ) -> str:
        dir_text = {
            "improving": "تحسّن ملحوظ",
            "declining": "تراجع يحتاج تدخلاً",
            "stable": "أداء مستقر",
            "mixed": "نتائج متباينة",
        }.get(overall, "أداء مستقر")

        parts = [f"مقارنةً بـ {prev.period_label}: {dir_text}."]
        if improving:
            parts.append(f"تحسّن في: {', '.join(improving)}.")
        if declining:
            parts.append(f"تراجع في: {', '.join(declining)} — يستحق الانتباه.")
        return " ".join(parts)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _overall_direction(trends: list[MetricTrend]) -> str:
        up   = sum(1 for t in trends if t.direction in ("up", "up_strong"))
        down = sum(1 for t in trends if t.direction in ("down", "down_strong"))
        total = len(trends)
        if total == 0:
            return "stable"
        if up > down and up >= total * 0.5:
            return "improving"
        if down > up and down >= total * 0.5:
            return "declining"
        if up == 0 and down == 0:
            return "stable"
        return "mixed"


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _pct(prev: float, curr: float) -> float:
    if prev == 0:
        return 100.0 if curr > 0 else 0.0
    return ((curr - prev) / prev) * 100.0


def _direction(delta: float) -> str:
    if delta > _STRONG:
        return "up_strong"
    if delta > _WEAK:
        return "up"
    if delta < -_STRONG:
        return "down_strong"
    if delta < -_WEAK:
        return "down"
    return "stable"


def _metric_sentence(
    label: str,
    delta: float,
    direction: str,
    prev: float,
    curr: float,
    key: str,
) -> str:
    abs_delta = abs(delta)

    if direction == "up_strong":
        emoji = "📈"
        verb = "ارتفع بشكل ملحوظ"
    elif direction == "up":
        emoji = "↑"
        verb = "ارتفع"
    elif direction == "down_strong":
        emoji = "📉"
        verb = "انخفض بشكل ملحوظ"
    elif direction == "down":
        emoji = "↓"
        verb = "انخفض"
    else:
        return f"{label}: مستقر (±{abs_delta:.1f}%)"

    # Format values based on metric type
    if key == "avg_engagement_rate":
        prev_fmt = f"{prev * 100:.2f}%"
        curr_fmt = f"{curr * 100:.2f}%"
    elif key in ("revenue", "avg_order_value"):
        prev_fmt = f"{prev:,.0f}"
        curr_fmt = f"{curr:,.0f}"
    elif key in ("conversion_rate", "returning_customer_rate"):
        prev_fmt = f"{prev * 100:.2f}%"
        curr_fmt = f"{curr * 100:.2f}%"
    else:
        prev_fmt = f"{int(prev):,}"
        curr_fmt = f"{int(curr):,}"

    return (
        f"{emoji} {label} {verb} {abs_delta:.1f}% "
        f"(من {prev_fmt} إلى {curr_fmt})"
    )
