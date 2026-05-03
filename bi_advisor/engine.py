from __future__ import annotations

from datetime import datetime

from .domain import (
    AdvisorOutput,
    BehavioralProfile,
    BusinessProfile,
    BusinessStateSummary,
    ContentIdea,
    DataSourceStatus,
    ExecutionPlan,
    ExperimentStep,
    Insight,
    LearningUpdate,
    MetricSnapshot,
    PlannedContentIdea,
    PostingSchedule,
    Recommendation,
    RecommendationOutcome,
    SuccessMetric,
    StrategyPerformance,
    WeeklyPlan,
)
from .evaluation import StrategyEvaluationEngine
from .memory import BusinessMemoryStore, deserialize_data_sources


class BusinessAdvisorEngine:
    """
    Deterministic but adaptive advisor loop.

    The engine updates a business-specific behavioral profile from computed
    strategy evaluations, then uses that profile to promote, demote, monitor,
    or re-test strategies during future recommendation cycles.
    """

    def __init__(self, memory_store: BusinessMemoryStore) -> None:
        self.memory_store = memory_store
        self.evaluation_engine = StrategyEvaluationEngine()

    def run(
        self,
        profile: BusinessProfile,
        new_snapshot: MetricSnapshot,
        data_sources: list[DataSourceStatus] | None = None,
    ) -> AdvisorOutput:
        context = self.memory_store.load_business_context(profile.business_id)
        snapshots = self._deserialize_snapshots(context["snapshots"])
        recommendations = self._deserialize_recommendations(context["recommendations"])
        outcomes = self._deserialize_outcomes(context["outcomes"])
        learning_updates = self._deserialize_learning_updates(context["learning_updates"])
        current_sources = data_sources or deserialize_data_sources(context.get("data_sources", []))

        previous_snapshot = snapshots[-1] if snapshots else None
        snapshots.append(new_snapshot)

        fresh_learning = self._generate_learning_updates(profile, recommendations, outcomes)
        learning_updates = self._merge_learning_updates(learning_updates, fresh_learning)
        behavioral_profile = self._build_behavioral_profile(
            profile=profile,
            snapshots=snapshots,
            learning_updates=learning_updates,
            recommendations=recommendations,
            outcomes=outcomes,
        )

        insights = self._generate_insights(
            profile=profile,
            previous_snapshot=previous_snapshot,
            current_snapshot=new_snapshot,
            behavioral_profile=behavioral_profile,
        )
        new_recommendations = self._generate_recommendations(
            profile=profile,
            previous_snapshot=previous_snapshot,
            current_snapshot=new_snapshot,
            behavioral_profile=behavioral_profile,
        )
        content_ideas = self._generate_content_ideas(profile, behavioral_profile, new_recommendations)
        reasoning_summary = self._build_reasoning_summary(behavioral_profile, insights, new_recommendations)

        recommendations.extend(new_recommendations)
        self.memory_store.save_business_context(
            profile=profile,
            snapshots=snapshots,
            recommendations=recommendations,
            outcomes=outcomes,
            learning_updates=learning_updates,
            behavioral_profile=behavioral_profile,
            data_sources=current_sources,
        )

        return AdvisorOutput(
            business_id=profile.business_id,
            generated_at=datetime.now(),
            state_summary=BusinessStateSummary(
                latest_snapshot_at=new_snapshot.captured_at,
                total_snapshots=len(snapshots),
                total_recommendations=len(recommendations),
                total_outcomes=len(outcomes),
                readiness=self._build_readiness(current_sources),
                behavioral_profile=behavioral_profile,
            ),
            data_backed_insights=insights,
            recommendations=new_recommendations,
            content_ideas=content_ideas,
            learning_updates=fresh_learning,
            reasoning_summary=reasoning_summary,
        )

    def record_outcome(
        self,
        profile: BusinessProfile,
        outcome: RecommendationOutcome,
    ) -> list[LearningUpdate]:
        context = self.memory_store.load_business_context(profile.business_id)
        snapshots = self._deserialize_snapshots(context["snapshots"])
        recommendations = self._deserialize_recommendations(context["recommendations"])
        outcomes = self._deserialize_outcomes(context["outcomes"])
        learning_updates = self._deserialize_learning_updates(context["learning_updates"])
        data_sources = deserialize_data_sources(context.get("data_sources", []))

        outcomes.append(outcome)
        fresh_learning = self._generate_learning_updates(profile, recommendations, [outcome])
        learning_updates = self._merge_learning_updates(learning_updates, fresh_learning)
        behavioral_profile = self._build_behavioral_profile(
            profile=profile,
            snapshots=snapshots,
            learning_updates=learning_updates,
            recommendations=recommendations,
            outcomes=outcomes,
        )

        self.memory_store.save_business_context(
            profile=profile,
            snapshots=snapshots,
            recommendations=recommendations,
            outcomes=outcomes,
            learning_updates=learning_updates,
            behavioral_profile=behavioral_profile,
            data_sources=data_sources,
        )
        return fresh_learning

    def evaluate_and_record_outcome(
        self,
        profile: BusinessProfile,
        recommendation_id: str,
        actual_snapshot: MetricSnapshot,
        measured_at: datetime | None = None,
        actual_result: str = "",
    ) -> RecommendationOutcome:
        context = self.memory_store.load_business_context(profile.business_id)
        recommendations = self._deserialize_recommendations(context["recommendations"])
        outcomes = self._deserialize_outcomes(context["outcomes"])

        recommendation = next(
            (item for item in recommendations if item.recommendation_id == recommendation_id),
            None,
        )
        if recommendation is None:
            raise ValueError(f"Recommendation {recommendation_id} not found for business {profile.business_id}")

        historical_scores = [
            item.performance_score
            for item in outcomes
            if self._recommendation_strategy(recommendations, item.recommendation_id) == recommendation.strategy_key
        ]
        actual_value = self._metric_value(actual_snapshot, recommendation.expected_metric)
        evaluation = self.evaluation_engine.evaluate(
            recommendation=recommendation,
            actual_value=actual_value,
            historical_scores=historical_scores,
        )

        outcome = RecommendationOutcome(
            recommendation_id=recommendation.recommendation_id,
            measured_at=measured_at or actual_snapshot.captured_at,
            expected_metric=recommendation.expected_metric,
            expected_value=evaluation.expected_value,
            actual_value=evaluation.actual_value,
            performance_delta=evaluation.performance_delta,
            classification=evaluation.classification,
            performance_score=evaluation.performance_score,
            confidence_adjustment=evaluation.confidence_adjustment,
            stability=evaluation.stability,
            risk_level=evaluation.risk_level,
            strategy_update=evaluation.strategy_update,
            actual_result=actual_result or evaluation.reasoning,
            outcome_score=evaluation.performance_score / 100.0,
            summary=evaluation.reasoning,
        )
        self.record_outcome(profile, outcome)
        return outcome

    def _generate_insights(
        self,
        profile: BusinessProfile,
        previous_snapshot: MetricSnapshot | None,
        current_snapshot: MetricSnapshot,
        behavioral_profile: BehavioralProfile,
    ) -> list[Insight]:
        if previous_snapshot is None:
            return [
                Insight(
                    title="Baseline established",
                    summary=(
                        f"Baseline stored for {profile.name}: revenue {current_snapshot.revenue:.2f}, "
                        f"leads {current_snapshot.leads}, conversion rate {current_snapshot.conversion_rate:.3f}, "
                        f"engagement rate {current_snapshot.content_engagement_rate:.3f}."
                    ),
                    evidence=[
                        f"Revenue: {current_snapshot.revenue:.2f}",
                        f"Leads: {current_snapshot.leads}",
                        f"Conversion rate: {current_snapshot.conversion_rate:.3f}",
                        f"Engagement rate: {current_snapshot.content_engagement_rate:.3f}",
                    ],
                    impact="medium",
                    reasoning="Future recommendations will use this baseline instead of generic assumptions.",
                )
            ]

        revenue_delta = self._pct_change(previous_snapshot.revenue, current_snapshot.revenue)
        leads_delta = self._pct_change(previous_snapshot.leads, current_snapshot.leads)
        conversion_delta = self._pct_change(previous_snapshot.conversion_rate, current_snapshot.conversion_rate)
        engagement_delta = self._pct_change(
            previous_snapshot.content_engagement_rate,
            current_snapshot.content_engagement_rate,
        )
        retention_delta = self._pct_change(
            previous_snapshot.returning_customer_rate,
            current_snapshot.returning_customer_rate,
        )

        insights: list[Insight] = []
        root_cause = self._infer_root_cause(
            revenue_delta=revenue_delta,
            leads_delta=leads_delta,
            conversion_delta=conversion_delta,
            engagement_delta=engagement_delta,
            retention_delta=retention_delta,
            previous_snapshot=previous_snapshot,
            current_snapshot=current_snapshot,
        )

        if abs(revenue_delta) >= 5 or abs(leads_delta) >= 5 or abs(conversion_delta) >= 5:
            insights.append(
                Insight(
                    title="Root cause",
                    summary=(
                        f"Revenue changed {revenue_delta:.1f}%, leads changed {leads_delta:.1f}%, "
                        f"and conversion changed {conversion_delta:.1f}%. {root_cause['summary']}"
                    ),
                    evidence=[
                        f"Previous revenue: {previous_snapshot.revenue:.2f}",
                        f"Current revenue: {current_snapshot.revenue:.2f}",
                        f"Previous leads: {previous_snapshot.leads}",
                        f"Current leads: {current_snapshot.leads}",
                        f"Previous conversion rate: {previous_snapshot.conversion_rate:.3f}",
                        f"Current conversion rate: {current_snapshot.conversion_rate:.3f}",
                    ],
                    impact="high",
                    reasoning=root_cause["reasoning"],
                )
            )

        if abs(engagement_delta) >= 5 or abs(retention_delta) >= 5:
            insights.append(
                Insight(
                    title="Demand driver",
                    summary=(
                        f"Content engagement changed {engagement_delta:.1f}% and returning customer rate changed "
                        f"{retention_delta:.1f}% versus the previous period. {root_cause['demand_summary']}"
                    ),
                    evidence=[
                        f"Previous engagement rate: {previous_snapshot.content_engagement_rate:.3f}",
                        f"Current engagement rate: {current_snapshot.content_engagement_rate:.3f}",
                        f"Previous returning customer rate: {previous_snapshot.returning_customer_rate:.3f}",
                        f"Current returning customer rate: {current_snapshot.returning_customer_rate:.3f}",
                    ],
                    impact="medium",
                    reasoning=root_cause["demand_reasoning"],
                )
            )

        if current_snapshot.ad_spend > 0:
            current_efficiency = current_snapshot.revenue / current_snapshot.ad_spend
            previous_efficiency = (
                previous_snapshot.revenue / previous_snapshot.ad_spend
                if previous_snapshot.ad_spend > 0
                else current_efficiency
            )
            efficiency_delta = self._pct_change(previous_efficiency, current_efficiency)
            if abs(efficiency_delta) >= 5:
                insights.append(
                    Insight(
                        title="Efficiency driver",
                        summary=(
                            f"Revenue per unit of spend changed {efficiency_delta:.1f}%, from "
                            f"{previous_efficiency:.2f} to {current_efficiency:.2f}. {root_cause['efficiency_summary']}"
                        ),
                        evidence=[
                            f"Previous ad spend: {previous_snapshot.ad_spend:.2f}",
                            f"Current ad spend: {current_snapshot.ad_spend:.2f}",
                            f"Previous revenue/spend: {previous_efficiency:.2f}",
                            f"Current revenue/spend: {current_efficiency:.2f}",
                        ],
                        impact="high" if abs(efficiency_delta) >= 10 else "medium",
                        reasoning=root_cause["efficiency_reasoning"],
                    )
                )

        if behavioral_profile.winning_patterns:
            insights.append(
                Insight(
                    title="Known winning pattern",
                    summary=f"Outcome memory shows a positive pattern: {behavioral_profile.winning_patterns[-1]}.",
                    evidence=behavioral_profile.winning_patterns[-2:] or behavioral_profile.winning_patterns,
                    impact="medium",
                    reasoning="This pattern comes from computed past strategy evaluations.",
                )
            )

        if behavioral_profile.decision_warnings:
            insights.append(
                Insight(
                    title="Decision warning",
                    summary=f"Past evaluation data flags a weak pattern: {behavioral_profile.decision_warnings[-1]}",
                    evidence=behavioral_profile.decision_warnings[-2:] or behavioral_profile.decision_warnings,
                    impact="medium",
                    reasoning="This warning comes from repeated below-expectation strategy evaluations.",
                )
            )

        for note in current_snapshot.notes:
            insights.append(
                Insight(
                    title="Operator note",
                    summary=note,
                    evidence=[note],
                    impact="low",
                    reasoning="Human notes are retained as supporting business context for later reasoning layers.",
                )
            )

        if not insights:
            insights.append(
                Insight(
                    title="Stable system",
                    summary=f"There is no dominant pattern in the data yet. {root_cause['summary']}",
                    evidence=[
                        f"Revenue delta: {revenue_delta:.1f}%",
                        f"Lead delta: {leads_delta:.1f}%",
                        f"Conversion delta: {conversion_delta:.1f}%",
                        f"Engagement delta: {engagement_delta:.1f}%",
                    ],
                    impact="low",
                    reasoning=root_cause["reasoning"],
                )
            )

        return insights

    def _generate_recommendations(
        self,
        profile: BusinessProfile,
        previous_snapshot: MetricSnapshot | None,
        current_snapshot: MetricSnapshot,
        behavioral_profile: BehavioralProfile,
    ) -> list[Recommendation]:
        performance_map = {
            item.strategy_key: item
            for item in behavioral_profile.strategy_performance
        }

        if previous_snapshot is None:
            return [
                Recommendation.create(
                    strategy_key="baseline_observation",
                    category="measurement",
                    title="Build the first reliable benchmark",
                    action="Collect one more reporting cycle before changing allocation aggressively.",
                    root_cause="Only one business snapshot exists, so there is not enough history to isolate a stable driver yet.",
                    why_this_matters=(
                        f"With only one snapshot, the advisor has revenue {current_snapshot.revenue:.2f}, leads {current_snapshot.leads}, "
                        "and conversion data, but no prior period for causal comparison."
                    ),
                    reason=[
                        "A single snapshot cannot show stable business behavior.",
                        "The next cycle will let the advisor compare movement instead of guessing from a one-off period.",
                    ],
                    expected_impact="Higher-quality decisions in the next cycle because the business will have a real baseline trend.",
                    expected_metric="revenue",
                    expected_value=current_snapshot.revenue,
                    confidence=0.95,
                    priority="high",
                    strategy_status="monitor",
                    execution_plan=self._build_execution_plan(
                        profile=profile,
                        strategy_key="baseline_observation",
                        title="Build the first reliable benchmark",
                        root_cause="Only one snapshot exists, so the immediate task is to create the first comparable baseline.",
                        why_this_matters=(
                            f"Revenue is {current_snapshot.revenue:.2f}, leads are {current_snapshot.leads}, and conversion rate is "
                            f"{current_snapshot.conversion_rate:.3f}, but there is no prior period to compare against."
                        ),
                        previous_snapshot=None,
                        current_snapshot=current_snapshot,
                        expected_metric="revenue",
                        expected_value=current_snapshot.revenue,
                        action_focus="measurement_baseline",
                    ),
                )
            ]

        candidates: list[Recommendation] = []
        pattern_threshold = 5.0
        revenue_delta = self._pct_change(previous_snapshot.revenue, current_snapshot.revenue)
        leads_delta = self._pct_change(previous_snapshot.leads, current_snapshot.leads)
        content_pattern_delta = self._pct_change(
            previous_snapshot.content_engagement_rate,
            current_snapshot.content_engagement_rate,
        )
        conversion_pattern_delta = self._pct_change(
            previous_snapshot.conversion_rate,
            current_snapshot.conversion_rate,
        )
        retention_pattern_delta = self._pct_change(
            previous_snapshot.returning_customer_rate,
            current_snapshot.returning_customer_rate,
        )
        root_cause = self._infer_root_cause(
            revenue_delta=self._pct_change(previous_snapshot.revenue, current_snapshot.revenue),
            leads_delta=self._pct_change(previous_snapshot.leads, current_snapshot.leads),
            conversion_delta=conversion_pattern_delta,
            engagement_delta=content_pattern_delta,
            retention_delta=retention_pattern_delta,
            previous_snapshot=previous_snapshot,
            current_snapshot=current_snapshot,
        )

        if content_pattern_delta >= pattern_threshold and (
            revenue_delta > 0 or root_cause["funnel_stage"] in {"top_of_funnel", "balanced_growth", "mixed"}
        ):
            candidates.append(
                self._build_adaptive_recommendation(
                    profile=profile,
                    strategy_key="scale_winning_content",
                    category="content",
                    title="Scale the current winning content pattern",
                    action="Expand the strongest hook across organic posts, paid creative tests, and landing page copy.",
                    root_cause=(
                        f"Content engagement increased {content_pattern_delta:.1f}% from {previous_snapshot.content_engagement_rate:.3f} to "
                        f"{current_snapshot.content_engagement_rate:.3f}, while revenue increased {revenue_delta:.1f}%."
                    ),
                    why_this_matters=(
                        f"The business is seeing stronger response at the top of the funnel and revenue is also up {revenue_delta:.1f}%, so this pattern is worth scaling."
                    ),
                    base_reason=[
                        f"Content engagement increased {content_pattern_delta:.1f}% from {previous_snapshot.content_engagement_rate:.3f} to {current_snapshot.content_engagement_rate:.3f}.",
                        root_cause["recommendation_driver"],
                    ],
                    expected_impact="Stronger top-of-funnel attention and better lead quality next cycle.",
                    expected_metric="content_engagement_rate",
                    expected_value=current_snapshot.content_engagement_rate * 1.12,
                    base_confidence=0.76,
                    default_status="scale",
                    performance_map=performance_map,
                    behavioral_profile=behavioral_profile,
                    recommended_content_types=["short-form video", "hook-led creative"],
                    execution_plan=self._build_execution_plan(
                        profile=profile,
                        strategy_key="scale_winning_content",
                        title="Scale the current winning content pattern",
                        root_cause=(
                            f"Content engagement increased {content_pattern_delta:.1f}% from {previous_snapshot.content_engagement_rate:.3f} to "
                            f"{current_snapshot.content_engagement_rate:.3f}, while revenue increased {revenue_delta:.1f}%."
                        ),
                        why_this_matters=(
                            f"Revenue is already up {revenue_delta:.1f}% and engagement is up {content_pattern_delta:.1f}%, so this strategy is producing measurable momentum."
                        ),
                        previous_snapshot=previous_snapshot,
                        current_snapshot=current_snapshot,
                        expected_metric="content_engagement_rate",
                        expected_value=current_snapshot.content_engagement_rate * 1.12,
                        action_focus="content_scale",
                    ),
                )
            )

        if conversion_pattern_delta <= -pattern_threshold and (
            abs(leads_delta) < pattern_threshold or root_cause["funnel_stage"] in {"conversion", "mixed"}
        ):
            candidates.append(
                self._build_adaptive_recommendation(
                    profile=profile,
                    strategy_key="repair_conversion_path",
                    category="conversion",
                    title="Repair conversion friction before adding more spend",
                    action="Audit landing page clarity, offer framing, and CTA alignment before increasing traffic volume.",
                    root_cause=(
                        f"Conversion rate fell {abs(conversion_pattern_delta):.1f}% from {previous_snapshot.conversion_rate:.3f} to "
                        f"{current_snapshot.conversion_rate:.3f} while leads moved {leads_delta:.1f}%."
                    ),
                    why_this_matters=(
                        "The business is losing value after visitors arrive, so fixing the funnel should create more revenue from current traffic."
                    ),
                    base_reason=[
                        f"Conversion rate fell {abs(conversion_pattern_delta):.1f}% from {previous_snapshot.conversion_rate:.3f} to {current_snapshot.conversion_rate:.3f}.",
                        root_cause["recommendation_driver"],
                    ],
                    expected_impact="Better monetization of existing demand and stronger conversion efficiency.",
                    expected_metric="conversion_rate",
                    expected_value=previous_snapshot.conversion_rate,
                    base_confidence=0.84,
                    default_status="test",
                    performance_map=performance_map,
                    behavioral_profile=behavioral_profile,
                    recommended_content_types=["offer clarity page", "objection handling content"],
                    execution_plan=self._build_execution_plan(
                        profile=profile,
                        strategy_key="repair_conversion_path",
                        title="Repair conversion friction before adding more spend",
                        root_cause=(
                            f"Conversion rate fell {abs(conversion_pattern_delta):.1f}% from {previous_snapshot.conversion_rate:.3f} to "
                            f"{current_snapshot.conversion_rate:.3f} while leads moved {leads_delta:.1f}%."
                        ),
                        why_this_matters=(
                            f"Conversion weakness is reducing monetization even though lead movement is only {leads_delta:.1f}%."
                        ),
                        previous_snapshot=previous_snapshot,
                        current_snapshot=current_snapshot,
                        expected_metric="conversion_rate",
                        expected_value=previous_snapshot.conversion_rate,
                        action_focus="conversion",
                    ),
                )
            )

        if retention_pattern_delta >= pattern_threshold and (
            revenue_delta > 0 or root_cause["funnel_stage"] in {"retention", "balanced_growth", "mixed"}
        ):
            candidates.append(
                self._build_adaptive_recommendation(
                    profile=profile,
                    strategy_key="push_retention_program",
                    category="retention",
                    title="Lean into repeat-revenue momentum",
                    action="Launch retention sequences such as reorder reminders, loyalty offers, and customer education content.",
                    root_cause=(
                        f"Returning customer rate increased {retention_pattern_delta:.1f}% from {previous_snapshot.returning_customer_rate:.3f} to "
                        f"{current_snapshot.returning_customer_rate:.3f}, while revenue increased {revenue_delta:.1f}%."
                    ),
                    why_this_matters=(
                        f"Repeat behavior is helping drive revenue, so strengthening retention should compound growth without relying only on new acquisition."
                    ),
                    base_reason=[
                        f"Returning customer rate increased {retention_pattern_delta:.1f}% from {previous_snapshot.returning_customer_rate:.3f} to {current_snapshot.returning_customer_rate:.3f}.",
                        root_cause["recommendation_driver"],
                    ],
                    expected_impact="Higher repeat revenue and lower dependence on new customer acquisition.",
                    expected_metric="returning_customer_rate",
                    expected_value=current_snapshot.returning_customer_rate * 1.06,
                    base_confidence=0.74,
                    default_status="test",
                    performance_map=performance_map,
                    behavioral_profile=behavioral_profile,
                    recommended_content_types=["email retention flow", "customer education"],
                    execution_plan=self._build_execution_plan(
                        profile=profile,
                        strategy_key="push_retention_program",
                        title="Lean into repeat-revenue momentum",
                        root_cause=(
                            f"Returning customer rate increased {retention_pattern_delta:.1f}% from {previous_snapshot.returning_customer_rate:.3f} to "
                            f"{current_snapshot.returning_customer_rate:.3f}, while revenue increased {revenue_delta:.1f}%."
                        ),
                        why_this_matters=(
                            f"Retention is already improving by {retention_pattern_delta:.1f}%, which means a focused retention plan can add incremental revenue efficiently."
                        ),
                        previous_snapshot=previous_snapshot,
                        current_snapshot=current_snapshot,
                        expected_metric="returning_customer_rate",
                        expected_value=current_snapshot.returning_customer_rate * 1.06,
                        action_focus="retention",
                    ),
                )
            )

        if not candidates:
            if root_cause["funnel_stage"] != "mixed":
                candidates.append(
                    self._root_cause_recommendation(
                        profile=profile,
                        previous_snapshot=previous_snapshot,
                        current_snapshot=current_snapshot,
                        root_cause=root_cause,
                        performance_map=performance_map,
                        revenue_delta=revenue_delta,
                        leads_delta=leads_delta,
                        conversion_delta=conversion_pattern_delta,
                        engagement_delta=content_pattern_delta,
                        retention_delta=retention_pattern_delta,
                    )
                )
            else:
                candidates.append(
                    Recommendation.create(
                        strategy_key="no_dominant_pattern",
                        category="measurement",
                        title="No dominant pattern in the data yet",
                        action="Wait for another cycle before changing strategy materially because the current signals are contradictory or too small.",
                        root_cause=root_cause["summary"],
                        why_this_matters=(
                            f"Revenue delta is {revenue_delta:.1f}%, lead delta is {leads_delta:.1f}%, conversion delta is "
                            f"{conversion_pattern_delta:.1f}%, engagement delta is {content_pattern_delta:.1f}%, and retention delta is {retention_pattern_delta:.1f}%."
                        ),
                        reason=[
                            f"Revenue delta is {revenue_delta:.1f}%, lead delta is {leads_delta:.1f}%, conversion delta is {conversion_pattern_delta:.1f}%, engagement delta is {content_pattern_delta:.1f}%, and retention delta is {retention_pattern_delta:.1f}%.",
                            root_cause["reasoning"],
                        ],
                        expected_impact="Avoids acting on weak or contradictory evidence.",
                        expected_metric="revenue",
                        expected_value=current_snapshot.revenue,
                        confidence=0.75,
                        priority="medium",
                        strategy_status="monitor",
                        execution_plan=self._build_execution_plan(
                            profile=profile,
                            strategy_key="no_dominant_pattern",
                            title="No dominant pattern in the data yet",
                            root_cause=root_cause["summary"],
                            why_this_matters=(
                                f"Revenue delta is {revenue_delta:.1f}%, leads delta is {leads_delta:.1f}%, conversion delta is {conversion_pattern_delta:.1f}%, "
                                f"engagement delta is {content_pattern_delta:.1f}%, and retention delta is {retention_pattern_delta:.1f}%."
                            ),
                            previous_snapshot=previous_snapshot,
                            current_snapshot=current_snapshot,
                            expected_metric="revenue",
                            expected_value=current_snapshot.revenue,
                            action_focus="mixed_signal_monitor",
                        ),
                    )
                )

        filtered_candidates = [
            item
            for item in candidates
            if not (item.strategy_status == "avoid" and item.priority == "low")
        ]
        if filtered_candidates:
            candidates = filtered_candidates

        candidates.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}[item.priority],
                -item.confidence,
            )
        )
        return candidates

    def _root_cause_recommendation(
        self,
        profile: BusinessProfile,
        previous_snapshot: MetricSnapshot,
        current_snapshot: MetricSnapshot,
        root_cause: dict[str, str],
        performance_map: dict[str, StrategyPerformance],
        revenue_delta: float,
        leads_delta: float,
        conversion_delta: float,
        engagement_delta: float,
        retention_delta: float,
    ) -> Recommendation:
        if root_cause["funnel_stage"] == "top_of_funnel":
            return self._build_adaptive_recommendation(
                profile=profile,
                strategy_key="restore_top_of_funnel_reach",
                category="acquisition",
                title="Restore top-of-funnel demand with higher-reach content",
                action=(
                    f"Increase high-reach content output and paid awareness distribution on {profile.channels[0] if profile.channels else 'the primary channel'}, "
                    "using stronger hooks and at least one new acquisition test."
                ),
                root_cause=(
                    f"Revenue changed {revenue_delta:.1f}% while conversion changed {conversion_delta:.1f}%, and engagement changed {engagement_delta:.1f}%, "
                    "which points to weaker top-of-funnel demand rather than a checkout problem."
                ),
                why_this_matters=(
                    f"Revenue is being constrained before conversion: leads moved {leads_delta:.1f}% and engagement moved {engagement_delta:.1f}% while "
                    f"conversion rate remains comparatively steadier at {current_snapshot.conversion_rate:.3f}."
                ),
                base_reason=[
                    f"Revenue changed {revenue_delta:.1f}% while conversion changed {conversion_delta:.1f}%, which indicates the loss is happening before conversion.",
                    f"Engagement changed {engagement_delta:.1f}% and leads changed {leads_delta:.1f}%, which points to weaker demand creation or reach.",
                ],
                expected_impact="More qualified traffic and stronger top-of-funnel volume in the next cycle.",
                expected_metric="leads",
                expected_value=max(current_snapshot.leads * 1.08, previous_snapshot.leads),
                base_confidence=0.81,
                default_status="test",
                performance_map=performance_map,
                behavioral_profile=self._build_behavioral_profile(profile, [previous_snapshot, current_snapshot], [], [], []),
                recommended_content_types=["short-form video", "awareness creative", "hook-led creative"],
                execution_plan=self._build_execution_plan(
                    profile=profile,
                    strategy_key="restore_top_of_funnel_reach",
                    title="Restore top-of-funnel demand with higher-reach content",
                    root_cause=(
                        f"Revenue changed {revenue_delta:.1f}% while conversion changed {conversion_delta:.1f}%, and engagement changed {engagement_delta:.1f}%, "
                        "which indicates weaker traffic or demand creation."
                    ),
                    why_this_matters=(
                        f"Leads changed {leads_delta:.1f}% and engagement changed {engagement_delta:.1f}%, so fewer high-intent users are entering the funnel."
                    ),
                    previous_snapshot=previous_snapshot,
                    current_snapshot=current_snapshot,
                    expected_metric="leads",
                    expected_value=max(current_snapshot.leads * 1.08, previous_snapshot.leads),
                    action_focus="top_of_funnel",
                ),
            )

        if root_cause["funnel_stage"] == "conversion":
            return self._build_adaptive_recommendation(
                profile=profile,
                strategy_key="repair_conversion_path",
                category="conversion",
                title="Fix the offer and funnel before scaling traffic",
                action="Improve landing page clarity, tighten offer presentation, and simplify checkout before increasing acquisition spend.",
                root_cause=(
                    f"Conversion fell {abs(conversion_delta):.1f}% while lead movement is {leads_delta:.1f}%, which points to a funnel or offer problem."
                ),
                why_this_matters=(
                    f"Traffic volume is comparatively steadier than conversion performance, so the business is losing value after users arrive."
                ),
                base_reason=[
                    f"Conversion rate fell {abs(conversion_delta):.1f}% from {previous_snapshot.conversion_rate:.3f} to {current_snapshot.conversion_rate:.3f}.",
                    f"Lead movement is {leads_delta:.1f}%, so the loss is happening after traffic arrives rather than before it.",
                ],
                expected_impact="Higher conversion from existing traffic and less wasted acquisition spend.",
                expected_metric="conversion_rate",
                expected_value=previous_snapshot.conversion_rate,
                base_confidence=0.86,
                default_status="test",
                performance_map=performance_map,
                behavioral_profile=self._build_behavioral_profile(profile, [previous_snapshot, current_snapshot], [], [], []),
                recommended_content_types=["offer clarity page", "pricing explainer", "checkout friction fix"],
                execution_plan=self._build_execution_plan(
                    profile=profile,
                    strategy_key="repair_conversion_path",
                    title="Fix the offer and funnel before scaling traffic",
                    root_cause=(
                        f"Conversion rate fell {abs(conversion_delta):.1f}% from {previous_snapshot.conversion_rate:.3f} to {current_snapshot.conversion_rate:.3f} while leads moved {leads_delta:.1f}%."
                    ),
                    why_this_matters=(
                        f"The business is converting less of similar demand, which directly pressures revenue efficiency and monetization."
                    ),
                    previous_snapshot=previous_snapshot,
                    current_snapshot=current_snapshot,
                    expected_metric="conversion_rate",
                    expected_value=previous_snapshot.conversion_rate,
                    action_focus="conversion",
                ),
            )

        if root_cause["funnel_stage"] == "retention":
            return self._build_adaptive_recommendation(
                profile=profile,
                strategy_key="stabilize_retention",
                category="retention",
                title="Strengthen post-purchase retention",
                action="Launch loyalty, re-engagement, and post-purchase education flows focused on repeat purchase behavior.",
                root_cause=(
                    f"Returning customer rate changed {retention_delta:.1f}% while revenue changed {revenue_delta:.1f}%, so retention is materially affecting revenue."
                ),
                why_this_matters=(
                    f"Repeat behavior is a meaningful revenue driver because lead movement is only {leads_delta:.1f}% while retention has shifted {retention_delta:.1f}%."
                ),
                base_reason=[
                    f"Returning customer rate changed {retention_delta:.1f}% and revenue changed {revenue_delta:.1f}%, so retention is materially affecting revenue.",
                    f"New lead movement is {leads_delta:.1f}%, which means repeat behavior is a meaningful driver in the current data.",
                ],
                expected_impact="More repeat revenue and stronger customer lifetime value.",
                expected_metric="returning_customer_rate",
                expected_value=max(current_snapshot.returning_customer_rate * 1.08, previous_snapshot.returning_customer_rate),
                base_confidence=0.8,
                default_status="test",
                performance_map=performance_map,
                behavioral_profile=self._build_behavioral_profile(profile, [previous_snapshot, current_snapshot], [], [], []),
                recommended_content_types=["loyalty campaign", "re-engagement flow", "post-purchase education"],
                execution_plan=self._build_execution_plan(
                    profile=profile,
                    strategy_key="stabilize_retention",
                    title="Strengthen post-purchase retention",
                    root_cause=(
                        f"Returning customer rate moved {retention_delta:.1f}% while revenue moved {revenue_delta:.1f}%, which shows retention is materially affecting revenue."
                    ),
                    why_this_matters=(
                        f"When repeat behavior changes this much, revenue can move even without major new-customer volume changes."
                    ),
                    previous_snapshot=previous_snapshot,
                    current_snapshot=current_snapshot,
                    expected_metric="returning_customer_rate",
                    expected_value=max(current_snapshot.returning_customer_rate * 1.08, previous_snapshot.returning_customer_rate),
                    action_focus="retention",
                ),
            )

        if root_cause["funnel_stage"] == "balanced_growth":
            return self._build_adaptive_recommendation(
                profile=profile,
                strategy_key="scale_growth_pattern",
                category="growth",
                title="Scale the strategy driving growth",
                action="Increase budget and replicate the current high-response strategy across the next channel and format variant.",
                root_cause=(
                    f"Revenue increased {revenue_delta:.1f}%, engagement increased {engagement_delta:.1f}%, and conversion moved {conversion_delta:.1f}%, which shows the strategy is driving broad growth."
                ),
                why_this_matters=(
                    f"Growth is not coming from a single isolated metric; demand response and monetization are both supporting expansion."
                ),
                base_reason=[
                    f"Revenue increased {revenue_delta:.1f}%, engagement increased {engagement_delta:.1f}%, and conversion moved {conversion_delta:.1f}%.",
                    "This combination shows that the current strategy is driving broader growth rather than a one-metric spike.",
                ],
                expected_impact="Faster growth while the current pattern is still performing.",
                expected_metric="revenue",
                expected_value=current_snapshot.revenue * 1.1,
                base_confidence=0.88,
                default_status="scale",
                performance_map=performance_map,
                behavioral_profile=self._build_behavioral_profile(profile, [previous_snapshot, current_snapshot], [], [], []),
                recommended_content_types=["winning creative replication", "cross-channel adaptation"],
                execution_plan=self._build_execution_plan(
                    profile=profile,
                    strategy_key="scale_growth_pattern",
                    title="Scale the strategy driving growth",
                    root_cause=(
                        f"Revenue is up {revenue_delta:.1f}%, engagement is up {engagement_delta:.1f}%, and conversion is {conversion_delta:.1f}% versus the prior period."
                    ),
                    why_this_matters=(
                        "The current strategy is performing across multiple stages of the funnel, which makes it worth scaling rather than just monitoring."
                    ),
                    previous_snapshot=previous_snapshot,
                    current_snapshot=current_snapshot,
                    expected_metric="revenue",
                    expected_value=current_snapshot.revenue * 1.1,
                    action_focus="growth_scale",
                ),
            )

        return Recommendation.create(
            strategy_key="mixed_signal_monitor",
            category="measurement",
            title="Monitor mixed signals before acting",
            action="Wait for another reporting cycle before making a large change.",
            root_cause=root_cause["summary"],
            why_this_matters=(
                f"Revenue delta is {revenue_delta:.1f}%, lead delta is {leads_delta:.1f}%, conversion delta is {conversion_delta:.1f}%, "
                f"engagement delta is {engagement_delta:.1f}%, and retention delta is {retention_delta:.1f}%."
            ),
            reason=[
                f"Revenue delta is {revenue_delta:.1f}%, lead delta is {leads_delta:.1f}%, conversion delta is {conversion_delta:.1f}%, engagement delta is {engagement_delta:.1f}%, and retention delta is {retention_delta:.1f}%.",
                root_cause["reasoning"],
            ],
            expected_impact="Reduces the chance of acting on unclear signals.",
            expected_metric="revenue",
            expected_value=current_snapshot.revenue,
            confidence=0.7,
            priority="medium",
            strategy_status="monitor",
            execution_plan=self._build_execution_plan(
                profile=profile,
                strategy_key="mixed_signal_monitor",
                title="Monitor mixed signals before acting",
                root_cause=root_cause["summary"],
                why_this_matters=(
                    f"Revenue delta is {revenue_delta:.1f}%, leads delta is {leads_delta:.1f}%, conversion delta is {conversion_delta:.1f}%, "
                    f"engagement delta is {engagement_delta:.1f}%, and retention delta is {retention_delta:.1f}%."
                ),
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
                expected_metric="revenue",
                expected_value=current_snapshot.revenue,
                action_focus="mixed_signal_monitor",
            ),
        )

    def _infer_root_cause(
        self,
        revenue_delta: float,
        leads_delta: float,
        conversion_delta: float,
        engagement_delta: float,
        retention_delta: float,
        previous_snapshot: MetricSnapshot,
        current_snapshot: MetricSnapshot,
    ) -> dict[str, str]:
        spend_delta = self._pct_change(previous_snapshot.ad_spend, current_snapshot.ad_spend)
        stable_conversion = abs(conversion_delta) < 5
        stable_leads = abs(leads_delta) < 5

        if revenue_delta < -5 and stable_conversion:
            return {
                "funnel_stage": "top_of_funnel",
                "summary": "Revenue is down while conversion is stable, so the likely driver is weaker traffic or weaker top-of-funnel demand rather than checkout performance.",
                "reasoning": "Stable conversion means the funnel is converting at roughly the same rate, so the revenue change is more likely coming from traffic volume, demand, or engagement quality.",
                "demand_summary": "This points to a top-of-funnel demand issue rather than a conversion issue.",
                "demand_reasoning": "When engagement or lead flow weakens while conversion stays stable, the bottleneck is usually earlier in the funnel.",
                "efficiency_summary": "Efficiency should be interpreted alongside reach and spend, not in isolation.",
                "efficiency_reasoning": "A higher or lower efficiency number can still coexist with weaker demand if total reach falls.",
                "recommendation_driver": "The metric relationship points to a top-of-funnel demand problem rather than a checkout problem.",
            }

        if engagement_delta < -5 and revenue_delta < -5:
            return {
                "funnel_stage": "top_of_funnel",
                "summary": "Engagement and revenue are both down, which points to a top-of-funnel weakness.",
                "reasoning": "When audience response weakens at the same time as revenue, the most likely driver is weaker reach, weaker content response, or weaker demand creation.",
                "demand_summary": "The demand signal is weakening at the top of the funnel.",
                "demand_reasoning": "Lower engagement and lower revenue together indicate that fewer users are responding strongly enough to enter or move through the funnel.",
                "efficiency_summary": "Efficiency changes should be read in the context of weaker demand creation.",
                "efficiency_reasoning": "Even stable efficiency cannot fully offset weaker demand if top-of-funnel response is falling.",
                "recommendation_driver": "The data points to a top-of-funnel weakness, so actions should focus on demand creation and engagement quality.",
            }

        if conversion_delta < -5 and stable_leads:
            return {
                "funnel_stage": "conversion",
                "summary": "Conversion is down while lead volume is stable, so the likely issue is the funnel, offer, or landing experience.",
                "reasoning": "Stable lead volume means people are still arriving, but fewer are completing the next step.",
                "demand_summary": "Demand generation looks relatively stable; the drop is occurring deeper in the funnel.",
                "demand_reasoning": "Because lead flow is not moving much, the main loss is happening after traffic acquisition.",
                "efficiency_summary": "Efficiency pressure is likely being created by weaker monetization rather than weaker traffic.",
                "efficiency_reasoning": "If conversion falls while inputs stay steady, the same traffic produces less revenue.",
                "recommendation_driver": "The data points to a funnel or offer problem, not a traffic problem.",
            }

        if revenue_delta < -5 and spend_delta < -5:
            return {
                "funnel_stage": "top_of_funnel",
                "summary": "Revenue is down and spend is also down, so reduced reach or acquisition volume is a likely driver.",
                "reasoning": "Lower spend often reduces traffic or impressions, which can reduce revenue even if unit efficiency improves.",
                "demand_summary": "Demand capture likely weakened because acquisition input also decreased.",
                "demand_reasoning": "Less spend usually means less reach unless another channel compensates.",
                "efficiency_summary": "Efficiency can rise even while revenue falls if spend is cut faster than revenue.",
                "efficiency_reasoning": "This is why efficiency should not be treated as proof of healthy growth on its own.",
                "recommendation_driver": "The likely issue is lower acquisition input or reach, not necessarily weaker conversion mechanics.",
            }

        if retention_delta > 5 and revenue_delta > 5:
            return {
                "funnel_stage": "retention",
                "summary": "Revenue and repeat behavior are both improving, which suggests retention is contributing to growth.",
                "reasoning": "When returning customer rate rises alongside revenue, repeat purchase behavior is likely part of the growth driver.",
                "demand_summary": "The strongest measurable demand signal is improving repeat behavior.",
                "demand_reasoning": "Retention is becoming a more meaningful share of revenue generation.",
                "efficiency_summary": "Higher retention can improve revenue efficiency by reducing reliance on fresh acquisition.",
                "efficiency_reasoning": "Repeat buyers usually lower the cost needed to generate the next unit of revenue.",
                "recommendation_driver": "The metric relationship suggests retention is contributing to growth, not just acquisition.",
            }

        if revenue_delta > 5 and engagement_delta > 5 and conversion_delta >= -5:
            return {
                "funnel_stage": "balanced_growth",
                "summary": "Revenue and engagement are both up without a material conversion decline, so stronger demand creation is likely driving growth.",
                "reasoning": "This pattern suggests better content response or audience quality is helping the business grow.",
                "demand_summary": "Top-of-funnel response is improving and is likely feeding downstream growth.",
                "demand_reasoning": "Higher engagement with stable conversion usually means more qualified demand is entering the funnel.",
                "efficiency_summary": "Efficiency should improve if stronger engagement continues to feed qualified demand.",
                "efficiency_reasoning": "Better audience response often produces better revenue per unit of spend over time.",
                "recommendation_driver": "The data suggests stronger demand creation is the primary growth driver.",
            }

        return {
            "funnel_stage": "mixed",
            "summary": "The metrics show movement, but the causal driver is mixed across demand, conversion, and retention signals.",
            "reasoning": "No single stage of the funnel fully explains the change, so the data should be treated as mixed rather than pattern-free.",
            "demand_summary": "Some demand signals moved, but not strongly enough to isolate a single root cause.",
            "demand_reasoning": "The current evidence spans multiple stages of the funnel.",
            "efficiency_summary": "Efficiency should be read together with revenue, spend, and conversion because no single metric explains the change.",
            "efficiency_reasoning": "The current snapshot has interacting effects rather than one clear driver.",
            "recommendation_driver": "The measurable relationships point to a mixed root cause rather than a single isolated issue.",
        }

    def _build_adaptive_recommendation(
        self,
        profile: BusinessProfile,
        strategy_key: str,
        category: str,
        title: str,
        action: str,
        root_cause: str,
        why_this_matters: str,
        base_reason: list[str],
        expected_impact: str,
        expected_metric: str,
        expected_value: float,
        base_confidence: float,
        default_status: str,
        performance_map: dict[str, StrategyPerformance],
        behavioral_profile: BehavioralProfile,
        recommended_content_types: list[str],
        execution_plan: ExecutionPlan,
    ) -> Recommendation:
        strategy_history = performance_map.get(strategy_key)
        reason = list(base_reason)
        confidence = base_confidence
        priority = "medium"
        strategy_status = default_status
        requires_validation = default_status in {"test", "monitor"}

        if strategy_history:
            total_outcomes = strategy_history.total_runs
            reason.append(
                f"Historical outcome memory for {strategy_key}: {strategy_history.average_performance_score:.1f} performance score across {total_outcomes} tracked runs."
            )

            if strategy_history.total_runs >= 2 and strategy_history.success_rate >= 0.65 and strategy_history.consistency_score >= 60:
                strategy_status = "scale"
                confidence = min(0.95, confidence + 0.16)
                priority = "high"
                requires_validation = False
                reason.append("This strategy has produced consistent successful evaluations, so the advisor promotes it.")
            elif strategy_history.failures >= 2 and strategy_history.average_performance_score <= 40:
                strategy_status = "avoid"
                confidence = max(0.2, confidence - 0.4)
                priority = "low"
                requires_validation = True
                action = f"Pause broad rollout and only revisit with a new hypothesis: {action}"
                reason.append("This strategy has repeatedly evaluated below expectations, so the advisor demotes it.")
            elif strategy_history.neutral >= 1 or (
                strategy_history.successes >= 1 and strategy_history.failures >= 1
            ):
                strategy_status = "test"
                confidence = max(0.45, confidence - 0.1)
                priority = "medium"
                requires_validation = True
                action = f"Run as a controlled re-test: {action}"
                reason.append("This strategy has mixed evaluation history, so the advisor keeps it experimental.")
            elif strategy_history.successes >= 1 and strategy_history.average_performance_score >= 75:
                strategy_status = "monitor"
                confidence = min(0.95, confidence + 0.08)
                priority = "high"
                reason.append("This strategy is performing above expectations, so the advisor keeps it active with elevated confidence.")
            elif strategy_history.failures >= 1 and strategy_history.average_performance_score <= 45:
                strategy_status = "avoid"
                confidence = max(0.3, confidence - 0.22)
                priority = "low"
                requires_validation = True
                action = f"Only consider a cautious validation test after revising the hypothesis: {action}"
                reason.append("This strategy previously evaluated below expectations, so the advisor downgrades it.")

        if strategy_key in behavioral_profile.preferred_growth_levers:
            confidence = min(0.95, confidence + 0.05)
            if strategy_status == "test":
                strategy_status = "monitor"
            priority = "high"
            requires_validation = False
            reason.append("The business behavioral profile already favors this growth lever.")

        if any(content_type in behavioral_profile.recommended_content_types for content_type in recommended_content_types):
            confidence = min(0.95, confidence + 0.03)
            reason.append("The content format suggested by this strategy matches what the business profile is increasingly favoring.")

        return Recommendation.create(
            strategy_key=strategy_key,
            category=category,
            title=title,
            action=action,
            root_cause=root_cause,
            why_this_matters=why_this_matters,
            reason=reason,
            expected_impact=expected_impact,
            expected_metric=expected_metric,
            expected_value=expected_value,
            confidence=confidence,
            priority=priority,
            strategy_status=strategy_status,
            execution_plan=execution_plan,
            requires_validation=requires_validation,
        )

    def _build_execution_plan(
        self,
        profile: BusinessProfile,
        strategy_key: str,
        title: str,
        root_cause: str,
        why_this_matters: str,
        previous_snapshot: MetricSnapshot | None,
        current_snapshot: MetricSnapshot,
        expected_metric: str,
        expected_value: float,
        action_focus: str,
    ) -> ExecutionPlan:
        primary_platform = profile.channels[0] if profile.channels else "Primary channel"
        secondary_platform = profile.channels[1] if len(profile.channels) > 1 else primary_platform
        audience = profile.audience_type
        format_signal = self._infer_format_signal(current_snapshot.notes)
        granularity_note = (
            "Current recommendations are business-level because the available data is aggregated by business, not by product, campaign, or audience segment."
        )

        if action_focus == "top_of_funnel":
            return ExecutionPlan(
                objective=f"Increase lead volume by restoring top-of-funnel demand and reach on {primary_platform}.",
                weekly_plan=WeeklyPlan(posts_per_week=5, platforms=[primary_platform, secondary_platform], frequency="1 post per weekday plus 2 boosted assets"),
                content_strategy=[
                    f"Use {format_signal} with hook-first creative because engagement and lead flow weakened before conversion.",
                    f"Prioritize awareness and problem-led creative on {primary_platform} to restore reach and qualified traffic.",
                    "Repurpose the strongest business message into both organic and paid formats to increase exposure efficiently.",
                    granularity_note,
                ],
                content_ideas=[
                    PlannedContentIdea(title=f"{audience} mistake {format_signal}", concept=f"Show the most common mistake {audience.lower()} makes before buying and how {profile.name} solves it."),
                    PlannedContentIdea(title="Before vs after demand story", concept=f"Contrast the audience's current state with the result after using {profile.name}."),
                    PlannedContentIdea(title="3 fast wins", concept=f"Deliver three immediate, useful tips that position {profile.name} as the fastest route to progress."),
                    PlannedContentIdea(title="Myth vs reality", concept=f"Challenge a common belief that stops {audience.lower()} from acting now."),
                    PlannedContentIdea(title="Founder POV", concept=f"A direct point-of-view piece explaining why typical alternatives fail {audience.lower()}."),
                ],
                hooks=[
                    f"If your {audience.lower()} content is getting ignored, this is why.",
                    "This is the mistake killing your reach right now.",
                    "Most people do this before they buy and it costs them results.",
                    "Here is what changed when we fixed the first 3 seconds.",
                    "If you want more qualified leads, start here.",
                ],
                posting_schedule=PostingSchedule(best_times=["11:00", "14:00", "20:00"], frequency="Post 5 times weekly, boost the top 2 posts within 24 hours"),
                experiment_plan=[
                    ExperimentStep(test_name="Hook test", variable_to_change="First 3-second opening line", success_signal=f"Engagement rate rises toward {expected_value:.3f}"),
                    ExperimentStep(test_name="Format test", variable_to_change="Reel vs static vs carousel", success_signal="Lead volume increases without lowering conversion"),
                    ExperimentStep(test_name="Channel test", variable_to_change=f"{secondary_platform} vs {primary_platform}", success_signal="Lower-cost reach and incremental leads"),
                ],
                paid_strategy=[
                    "Boost the two posts with the highest saves and completion rate.",
                    "Allocate awareness budget to the best-performing hook-led asset first.",
                    "Use paid support to restore reach while monitoring cost per lead.",
                ],
                success_metrics=[
                    SuccessMetric(metric="Leads", target=f">= {expected_value:.0f}", why_it_matters="Lead volume is the clearest top-of-funnel recovery signal."),
                    SuccessMetric(metric="Content engagement rate", target=f"> {current_snapshot.content_engagement_rate:.3f}", why_it_matters="Higher engagement should confirm improved audience response."),
                    SuccessMetric(metric="Conversion rate", target=f">= {current_snapshot.conversion_rate:.3f}", why_it_matters="Traffic recovery should not come at the cost of lower traffic quality."),
                ],
            )

        if action_focus == "conversion":
            return ExecutionPlan(
                objective="Recover lost conversion by improving clarity, offer strength, and checkout flow.",
                weekly_plan=WeeklyPlan(posts_per_week=3, platforms=[primary_platform, secondary_platform], frequency="3 conversion-support posts weekly plus landing page updates"),
                content_strategy=[
                    f"Use objection-handling and offer-clarity content because conversion fell while lead movement stayed comparatively stable.",
                    "Focus on pricing clarity, proof, and friction reduction instead of awareness-heavy content.",
                    "Align organic and paid messaging with the revised landing page promise so the funnel says the same thing at every step.",
                    granularity_note,
                ],
                content_ideas=[
                    PlannedContentIdea(title="What you actually get", concept=f"Walk through the {profile.name} offer in plain language and show exactly what is included."),
                    PlannedContentIdea(title="Price vs value breakdown", concept="Explain why the price is justified using outcomes, time saved, or result gained."),
                    PlannedContentIdea(title="Checkout FAQ", concept="Answer the five objections most likely to stop a ready-to-buy visitor."),
                    PlannedContentIdea(title="Customer proof story", concept=f"Show a customer outcome with specific before/after details tied to {profile.value_proposition or 'the offer'} ."),
                    PlannedContentIdea(title="Bundle comparison", concept="Compare the current offer options to make the decision easier and reduce hesitation."),
                ],
                hooks=[
                    "Still unsure what you actually get? Start here.",
                    "This is the objection we hear most and the real answer.",
                    "Why customers choose this instead of the cheaper option.",
                    "If you are visiting and not buying, this is probably why.",
                    "Here is what changed after we simplified the offer.",
                ],
                posting_schedule=PostingSchedule(best_times=["12:00", "18:00", "21:00"], frequency="Post 3 conversion-support assets weekly and update landing assets every 3 days"),
                experiment_plan=[
                    ExperimentStep(test_name="Landing page clarity test", variable_to_change="Headline and subheadline", success_signal=f"Conversion moves back toward {expected_value:.3f}"),
                    ExperimentStep(test_name="Offer framing test", variable_to_change="Bundle vs single-product offer", success_signal="Higher conversion and higher average order confidence"),
                    ExperimentStep(test_name="Checkout friction test", variable_to_change="Checkout steps and trust blocks", success_signal="Lower abandonment and higher completed purchases"),
                ],
                paid_strategy=[
                    "Pause major spend increases until conversion improves.",
                    "Retarget warm traffic with proof-driven creatives only.",
                    "Boost assets that answer objections directly instead of top-of-funnel awareness content.",
                ],
                success_metrics=[
                    SuccessMetric(metric="Conversion rate", target=f">= {expected_value:.3f}", why_it_matters="This is the core problem the plan is designed to fix."),
                    SuccessMetric(metric="Revenue per visitor", target="Increase versus current baseline", why_it_matters="Better conversion should lift monetization efficiency."),
                    SuccessMetric(metric="Checkout completion", target="Increase week over week", why_it_matters="This confirms reduced funnel friction."),
                ],
            )

        if action_focus == "retention":
            return ExecutionPlan(
                objective="Increase repeat purchase behavior and reduce reliance on new customer acquisition.",
                weekly_plan=WeeklyPlan(posts_per_week=4, platforms=["Email", primary_platform], frequency="2 retention emails plus 2 customer education or proof posts weekly"),
                content_strategy=[
                    "Use loyalty, re-engagement, and post-purchase education because repeat behavior is directly affecting revenue.",
                    "Prioritize customer outcome reminders and product usage content to increase repeat purchase intent.",
                    f"Build content around repeat value for {audience.lower()}, not just initial acquisition messaging.",
                    granularity_note,
                ],
                content_ideas=[
                    PlannedContentIdea(title="Why customers come back", concept=f"Show the repeat-purchase reasons {profile.name} customers mention most."),
                    PlannedContentIdea(title="Best way to use it", concept=f"Teach customers how to get more value from {profile.name} so they are more likely to buy again."),
                    PlannedContentIdea(title="Customer routine", concept=f"Share a realistic {audience.lower()} routine that naturally leads to repeat use."),
                    PlannedContentIdea(title="Reorder reminder", concept="Create a timely reminder tied to replenishment timing or natural usage cycle."),
                    PlannedContentIdea(title="Loyalty reward reveal", concept="Explain the retention incentive and why repeat customers benefit now."),
                ],
                hooks=[
                    "Most customers come back for this reason.",
                    "If you already bought once, do this next.",
                    "This is the easiest way to get more value from your purchase.",
                    "Running low? Here is when most people reorder.",
                    "The loyalty perk most customers miss.",
                ],
                posting_schedule=PostingSchedule(best_times=["10:00", "13:00", "19:00"], frequency="2 retention emails weekly plus 2 social/customer proof posts"),
                experiment_plan=[
                    ExperimentStep(test_name="Re-engagement timing test", variable_to_change="Days since purchase before first reminder", success_signal=f"Returning customer rate rises toward {expected_value:.3f}"),
                    ExperimentStep(test_name="Offer test", variable_to_change="Loyalty reward vs educational reminder", success_signal="Higher repeat order rate"),
                    ExperimentStep(test_name="Message test", variable_to_change="Benefit-led vs urgency-led reactivation copy", success_signal="Higher click-through and reorder rate"),
                ],
                paid_strategy=[
                    "Boost customer proof and product usage content to recent buyers and warm audiences.",
                    "Use paid remarketing only for repeat-intent segments, not broad cold traffic.",
                    "Prioritize low-cost retention remarketing before expanding acquisition spend.",
                ],
                success_metrics=[
                    SuccessMetric(metric="Returning customer rate", target=f">= {expected_value:.3f}", why_it_matters="This is the direct retention recovery metric."),
                    SuccessMetric(metric="Repeat revenue", target="Increase week over week", why_it_matters="Retention should convert directly into revenue lift."),
                    SuccessMetric(metric="Email re-engagement rate", target="Increase across post-purchase campaigns", why_it_matters="This shows retention messaging is resonating."),
                ],
            )

        if action_focus == "content_scale":
            return ExecutionPlan(
                objective=f"Scale the winning {format_signal} pattern because engagement rose from {previous_snapshot.content_engagement_rate:.3f} to {current_snapshot.content_engagement_rate:.3f}.",
                weekly_plan=WeeklyPlan(posts_per_week=5, platforms=[primary_platform, secondary_platform], frequency=f"4 {format_signal} posts plus 1 proof-led adaptation weekly"),
                content_strategy=[
                    f"Double down on {format_signal} because the latest snapshot shows it is the clearest top-of-funnel growth signal.",
                    "Keep the same hook structure and vary only proof, objection, or angle so we preserve what is already working.",
                    f"Translate the winning message from {primary_platform} into {secondary_platform} before broadening further.",
                    granularity_note,
                ],
                content_ideas=[
                    PlannedContentIdea(title=f"{format_signal.title()} with direct hook", concept=f"Use the same direct-hook style that lifted engagement to {current_snapshot.content_engagement_rate:.3f}, then swap in a stronger proof point."),
                    PlannedContentIdea(title="Proof-led variation", concept="Turn a customer result into a tighter proof-driven version of the winning format."),
                    PlannedContentIdea(title="Objection-led adaptation", concept="Take the same hook and reframe it around the audience's main hesitation."),
                    PlannedContentIdea(title="Cross-platform cutdown", concept=f"Adapt the winning {primary_platform} idea into a shorter {secondary_platform} version without changing the core message."),
                    PlannedContentIdea(title="Comment-response content", concept="Use the highest-signal audience questions as the next set of winning hook variants."),
                ],
                hooks=[
                    "This is the exact shift that improved response last week.",
                    "Why this message is landing better right now.",
                    "If this got your attention, here is the next step.",
                    "The strongest response came from this angle, so here is version two.",
                    "Most people miss this, and that is why this format is working.",
                ],
                posting_schedule=PostingSchedule(best_times=["11:00", "15:00", "20:00"], frequency=f"Publish 5 times weekly with {format_signal}-first priority"),
                experiment_plan=[
                    ExperimentStep(test_name="Hook carryover test", variable_to_change="Same hook, different proof", success_signal=f"Engagement stays above {current_snapshot.content_engagement_rate:.3f}"),
                    ExperimentStep(test_name="Platform adaptation test", variable_to_change=f"{primary_platform} original vs {secondary_platform} adaptation", success_signal="Strong engagement without losing downstream conversion"),
                    ExperimentStep(test_name="Proof density test", variable_to_change="Single proof point vs multi-proof version", success_signal="Higher saves, clicks, or qualified traffic"),
                ],
                paid_strategy=[
                    f"Boost the top-performing {format_signal} asset first.",
                    "Only amplify content that preserves the exact opening hook and early audience retention pattern.",
                    "Increase spend gradually so the team can tell whether the winning message still holds at higher reach.",
                ],
                success_metrics=[
                    SuccessMetric(metric="Content engagement rate", target=f">= {expected_value:.3f}", why_it_matters="This is the clearest measurable signal behind the recommendation."),
                    SuccessMetric(metric="Leads", target="Increase from current baseline", why_it_matters="Higher engagement should translate into more qualified demand."),
                    SuccessMetric(metric="Revenue", target="Continue positive movement week over week", why_it_matters="The winning content pattern should support actual business growth, not vanity engagement."),
                ],
            )

        if action_focus == "growth_scale":
            return ExecutionPlan(
                objective="Scale the current winning growth pattern across more reach and more placements.",
                weekly_plan=WeeklyPlan(posts_per_week=6, platforms=[primary_platform, secondary_platform], frequency="Daily posting plus 2 paid amplification pushes"),
                content_strategy=[
                    "Replicate the highest-response format because both revenue and engagement are already increasing.",
                    "Extend the same winning message across an additional placement before the pattern cools down.",
                    "Keep proof and high-energy hook content at the center of the content mix.",
                    granularity_note,
                ],
                content_ideas=[
                    PlannedContentIdea(title="Winning hook variation 1", concept="Keep the same hook structure and change the proof example."),
                    PlannedContentIdea(title="Winning hook variation 2", concept="Adapt the best-performing message into a stronger visual format."),
                    PlannedContentIdea(title="Cross-channel adaptation", concept="Take the winning idea and rebuild it for the second platform."),
                    PlannedContentIdea(title="Case-study sprint", concept="Publish a compact proof-led series over multiple days."),
                    PlannedContentIdea(title="Fast objection flip", concept="Address the main objection without changing the winning core message."),
                ],
                hooks=[
                    "This is the exact message currently driving growth.",
                    "We doubled down on this because it is already working.",
                    "If this angle is resonating, here is the next version.",
                    "The pattern behind our strongest-performing content right now.",
                    "This is the message we would scale first.",
                ],
                posting_schedule=PostingSchedule(best_times=["11:00", "15:00", "20:00"], frequency="Post daily and boost the top 2 winners within 12 hours"),
                experiment_plan=[
                    ExperimentStep(test_name="Channel expansion", variable_to_change=f"Replicate winning creative on {secondary_platform}", success_signal=f"{expected_metric} moves toward {expected_value:.2f}"),
                    ExperimentStep(test_name="Budget expansion", variable_to_change="Increase spend on winning assets by 15-20%", success_signal="Revenue rises without material efficiency loss"),
                    ExperimentStep(test_name="Proof variant test", variable_to_change="Different proof story using same hook", success_signal="Similar or better engagement and revenue lift"),
                ],
                paid_strategy=[
                    "Increase spend first on the assets already driving the best response.",
                    "Boost the winning message across one adjacent channel before broad expansion.",
                    "Protect efficiency by scaling in steps, not all at once.",
                ],
                success_metrics=[
                    SuccessMetric(metric=expected_metric, target=f">= {expected_value:.2f}", why_it_matters="The plan is designed to scale the current winning pattern."),
                    SuccessMetric(metric="Content engagement rate", target=f"> {current_snapshot.content_engagement_rate:.3f}", why_it_matters="Engagement should stay strong while scaling."),
                    SuccessMetric(metric="Marketing efficiency", target="Stable or higher while scaling", why_it_matters="Growth should not come from wasteful spend increases."),
                ],
            )

        return ExecutionPlan(
            objective="Collect one more clean cycle of evidence before scaling or cutting strategy.",
            weekly_plan=WeeklyPlan(posts_per_week=3, platforms=[primary_platform], frequency="Maintain a steady weekly cadence"),
            content_strategy=[
                "Keep content output consistent so the next reporting cycle is easier to compare.",
                "Avoid large strategic changes until the signal becomes clearer.",
                "Preserve at least one control message so new changes can be measured properly.",
            ],
            content_ideas=[
                PlannedContentIdea(title="Baseline proof post", concept="Reuse a known message to preserve a comparison point."),
                PlannedContentIdea(title="Audience question post", concept="Use comments or replies to surface what is blocking action."),
                PlannedContentIdea(title="Offer reminder", concept="Restate the core value proposition without changing the angle materially."),
                PlannedContentIdea(title="Simple customer proof", concept="Use one customer result to keep trust signals steady."),
                PlannedContentIdea(title="Short insight post", concept="Publish one concise educational post to keep engagement stable."),
            ],
            hooks=[
                "Here is the simplest version of what we do.",
                "If you are still deciding, start here.",
                "This is the one thing customers tell us most.",
                "A quick reminder of why this matters.",
                "Before we change the strategy, this is what we are watching.",
            ],
            posting_schedule=PostingSchedule(best_times=["12:00", "19:00"], frequency="3 steady posts per week"),
            experiment_plan=[
                ExperimentStep(test_name="Control period", variable_to_change="No major strategic change", success_signal="Cleaner next-period comparison"),
                ExperimentStep(test_name="Single-variable test", variable_to_change="Only one creative change at a time", success_signal="Clearer attribution of what moved"),
                ExperimentStep(test_name="Timing check", variable_to_change="Posting time only", success_signal="Small, measurable engagement differences"),
            ],
            paid_strategy=[
                "Limit paid changes until the next cycle clarifies the signal.",
                "Only support the most stable asset with light budget.",
                "Avoid broad budget expansion while the signal is mixed.",
            ],
            success_metrics=[
                SuccessMetric(metric=expected_metric, target=f">= {expected_value:.2f}", why_it_matters="Provides a clear benchmark for the next cycle."),
                SuccessMetric(metric="Signal clarity", target="Fewer contradictory movements across core metrics", why_it_matters="The next decision should rest on clearer evidence."),
            ],
        )

    def _infer_format_signal(self, notes: list[str]) -> str:
        combined = " ".join(notes).lower()
        if "reel" in combined or "video" in combined:
            return "reel"
        if "carousel" in combined:
            return "carousel"
        if "email" in combined:
            return "email"
        return "content"

    def _generate_content_ideas(
        self,
        profile: BusinessProfile,
        behavioral_profile: BehavioralProfile,
        recommendations: list[Recommendation],
    ) -> list[ContentIdea]:
        primary_channel = (
            behavioral_profile.recommended_channels[0]
            if behavioral_profile.recommended_channels
            else (profile.channels[0] if profile.channels else "content")
        )
        audience = profile.audience_type.lower()
        lead_strategy = recommendations[0].strategy_key if recommendations else "general_positioning"
        winning_pattern = (
            behavioral_profile.winning_patterns[0]
            if behavioral_profile.winning_patterns
            else "problem-solution clarity"
        )
        risky_pattern = (
            behavioral_profile.risky_patterns[0]
            if behavioral_profile.risky_patterns
            else "weak generic messaging"
        )

        return [
            ContentIdea(
                title=f"Why {profile.name} works for {audience}",
                angle=f"Use the proven pattern '{winning_pattern}' to frame a concrete problem-to-outcome narrative.",
                channel=primary_channel,
                rationale="This ties content production to the strongest known business-specific performance pattern.",
                linked_strategy=lead_strategy,
            ),
            ContentIdea(
                title="Customer proof breakdown",
                angle="Turn a real result into a step-by-step breakdown of what changed and why it mattered.",
                channel=primary_channel,
                rationale="Proof-driven content supports strategies that are already showing signs of success.",
                linked_strategy=lead_strategy,
            ),
            ContentIdea(
                title="Objection handling content",
                angle=f"Address objections linked to the risky pattern '{risky_pattern}' so weak areas do not repeat.",
                channel=primary_channel,
                rationale="The advisor should use past failures to shape what gets tested or clarified next.",
                linked_strategy=lead_strategy,
            ),
        ]

    def _generate_learning_updates(
        self,
        profile: BusinessProfile,
        recommendations: list[Recommendation],
        outcomes: list[RecommendationOutcome],
    ) -> list[LearningUpdate]:
        recommendation_map = {
            item.recommendation_id: item
            for item in recommendations
        }
        updates: list[LearningUpdate] = []

        for outcome in outcomes:
            recommendation = recommendation_map.get(outcome.recommendation_id)
            if recommendation is None:
                continue

            if outcome.classification == "success":
                updates.append(
                    LearningUpdate(
                        strategy_key=recommendation.strategy_key,
                        outcome="worked",
                        what_worked=recommendation.title,
                        what_failed="No major failure detected in this outcome.",
                        scale_next=f"Scale {recommendation.strategy_key} more aggressively in future cycles.",
                        pause_next="Do not pause this strategy unless later data reverses the pattern.",
                        test_next="Test adjacent variations to expand the winning pattern without changing its core message.",
                        lesson=f"{recommendation.strategy_key} is a proven positive lever for {profile.name}.",
                        evidence=outcome.summary,
                        confidence=min(0.95, outcome.performance_score / 100.0),
                        adjustment="Promote this strategy and let it influence future priority and confidence scoring.",
                        updated_at=outcome.measured_at,
                    )
                )
            elif outcome.classification == "moderate_success":
                updates.append(
                    LearningUpdate(
                        strategy_key=recommendation.strategy_key,
                        outcome="worked",
                        what_worked=f"{recommendation.title} met or slightly exceeded expectations.",
                        what_failed="No major failure occurred, but the edge was not strong enough to justify an aggressive rollout.",
                        scale_next=f"Keep {recommendation.strategy_key} active and expand carefully if the next cycle confirms the pattern.",
                        pause_next="No immediate pause needed, but avoid overcommitting until the result repeats.",
                        test_next="Validate the same play with one adjacent variation to see if it becomes a repeatable win.",
                        lesson=f"{recommendation.strategy_key} is showing promising early evidence for {profile.name}.",
                        evidence=outcome.summary,
                        confidence=min(0.85, outcome.performance_score / 100.0),
                        adjustment="Increase confidence modestly and treat this strategy as monitor-ready rather than fully scaled.",
                        updated_at=outcome.measured_at,
                    )
                )
            elif outcome.classification == "failure":
                updates.append(
                    LearningUpdate(
                        strategy_key=recommendation.strategy_key,
                        outcome="failed",
                        what_worked="No durable positive pattern was confirmed.",
                        what_failed=recommendation.title,
                        scale_next="Scale an alternative strategy instead of this one.",
                        pause_next=f"Pause {recommendation.strategy_key} until a new hypothesis or different execution approach is defined.",
                        test_next="If revisited, run only a tightly scoped validation test with revised messaging or targeting.",
                        lesson=f"{recommendation.strategy_key} is weak for {profile.name} in its current form.",
                        evidence=outcome.summary,
                        confidence=0.85,
                        adjustment="Demote this strategy and surface decision warnings to prevent repeated low-quality recommendations.",
                        updated_at=outcome.measured_at,
                    )
                )
            else:
                updates.append(
                    LearningUpdate(
                        strategy_key=recommendation.strategy_key,
                        outcome="mixed",
                        what_worked=f"Some aspects of {recommendation.title} showed partial promise.",
                        what_failed="The result was not strong or stable enough to justify a full rollout.",
                        scale_next="Do not scale broadly yet.",
                        pause_next="Pause large allocation changes until the ambiguous result is clarified.",
                        test_next=f"Re-test {recommendation.strategy_key} with one narrower variable change.",
                        lesson=f"{recommendation.strategy_key} remains ambiguous and should stay experimental for {profile.name}.",
                        evidence=outcome.summary,
                        confidence=max(0.5, outcome.performance_score / 100.0),
                        adjustment="Keep this strategy in test mode and wait for clearer evidence before promoting or avoiding it.",
                        updated_at=outcome.measured_at,
                    )
                )

        return updates

    def _build_behavioral_profile(
        self,
        profile: BusinessProfile,
        snapshots: list[MetricSnapshot],
        learning_updates: list[LearningUpdate],
        recommendations: list[Recommendation],
        outcomes: list[RecommendationOutcome],
    ) -> BehavioralProfile:
        strategy_lookup = self._summarize_strategy_performance(profile, recommendations, outcomes)
        preferred_growth_levers = [
            key for key, performance in strategy_lookup.items()
            if performance.recommended_posture in {"scale", "monitor"}
        ][-4:]
        winning_patterns = [
            f"{update.strategy_key}:{update.scale_next}"
            for update in learning_updates
            if update.outcome == "worked"
        ][-4:]
        weak_patterns = [
            f"{update.strategy_key}:{update.pause_next}"
            for update in learning_updates
            if update.outcome == "failed"
        ][-4:]
        risky_patterns = [
            update.strategy_key
            for update in learning_updates
            if update.outcome in {"failed", "mixed"}
        ][-4:]
        decision_warnings = [
            update.adjustment
            for update in learning_updates
            if update.outcome == "failed"
        ][-4:]

        return BehavioralProfile(
            business_id=profile.business_id,
            preferred_growth_levers=preferred_growth_levers,
            winning_patterns=winning_patterns,
            weak_patterns=weak_patterns,
            risky_patterns=risky_patterns,
            recommended_channels=self._build_recommended_channels(profile, strategy_lookup),
            recommended_content_types=self._build_recommended_content_types(strategy_lookup),
            decision_warnings=decision_warnings,
            trend_summary=self._build_trend_summary(snapshots),
            strategy_performance=list(strategy_lookup.values()),
            last_updated=datetime.now(),
        )

    def _summarize_strategy_performance(
        self,
        profile: BusinessProfile,
        recommendations: list[Recommendation],
        outcomes: list[RecommendationOutcome],
    ) -> dict[str, StrategyPerformance]:
        recommendation_map = {
            item.recommendation_id: item
            for item in recommendations
        }
        strategy_summary: dict[str, StrategyPerformance] = {}

        for outcome in outcomes:
            recommendation = recommendation_map.get(outcome.recommendation_id)
            if recommendation is None:
                continue

            record = strategy_summary.setdefault(
                recommendation.strategy_key,
                StrategyPerformance(
                    strategy_key=recommendation.strategy_key,
                    strategy_label=recommendation.title,
                    recommended_channels=profile.channels[:2],
                    recommended_content_types=self._content_types_for_strategy(recommendation.strategy_key),
                ),
            )

            if outcome.classification in {"success", "moderate_success"}:
                record.successes += 1
            elif outcome.classification == "failure":
                record.failures += 1
            else:
                record.neutral += 1

            record.confidence_history.append(outcome.performance_score / 100.0)
            record.last_outcome_score = outcome.performance_score / 100.0
            record.last_summary = outcome.summary
            record.total_runs = record.successes + record.failures + record.neutral
            record.average_outcome_score = (
                sum(record.confidence_history) / record.total_runs if record.total_runs else 0.5
            )
            record.success_rate = record.successes / record.total_runs if record.total_runs else 0.0
            record.average_performance_score = (
                sum(score * 100 for score in record.confidence_history) / record.total_runs
                if record.total_runs
                else 50.0
            )
            record.consistency_score = self._consistency_score(
                [score * 100 for score in record.confidence_history]
            )
            record.recommended_posture = self._resolve_strategy_posture(record)

        return strategy_summary

    def _resolve_strategy_posture(self, record: StrategyPerformance) -> str:
        if record.total_runs >= 2 and record.success_rate >= 0.65 and record.consistency_score >= 60:
            return "scale"
        if record.failures >= 2 and record.average_performance_score <= 40:
            return "avoid"
        if record.failures >= 1 and record.successes == 0 and record.average_performance_score <= 45:
            return "avoid"
        if record.neutral >= 1 or (record.successes >= 1 and record.failures >= 1):
            return "test"
        if record.successes >= 1 and record.average_performance_score >= 75:
            return "monitor"
        return "monitor"

    def _build_recommended_channels(
        self,
        profile: BusinessProfile,
        strategy_lookup: dict[str, StrategyPerformance],
    ) -> list[str]:
        if any(item.recommended_posture in {"scale", "monitor"} for item in strategy_lookup.values()):
            return profile.channels[:2] or ["content"]
        return profile.channels[:1] or ["content"]

    def _build_recommended_content_types(
        self,
        strategy_lookup: dict[str, StrategyPerformance],
    ) -> list[str]:
        content_types: list[str] = []
        for strategy in strategy_lookup.values():
            if strategy.recommended_posture in {"scale", "test", "monitor"}:
                content_types.extend(strategy.recommended_content_types)
        if not content_types:
            return ["problem-solution content"]
        return list(dict.fromkeys(content_types))[:4]

    def _build_reasoning_summary(
        self,
        behavioral_profile: BehavioralProfile,
        insights: list[Insight],
        recommendations: list[Recommendation],
    ) -> list[str]:
        summary = [
            f"The advisor evaluated {len(insights)} data-backed signals from the latest snapshot and historical business memory.",
            f"The business now has {len(behavioral_profile.strategy_performance)} tracked strategy types with computed outcome memory.",
        ]
        if behavioral_profile.preferred_growth_levers:
            summary.append(
                f"Preferred growth levers are now biased toward {', '.join(behavioral_profile.preferred_growth_levers)}."
            )
        if behavioral_profile.decision_warnings:
            summary.append("Repeated weak strategies are now flagged so they are not recommended again without caution.")
        if recommendations:
            top = recommendations[0]
            summary.append(
                f"The top recommendation is '{top.title}' with {top.strategy_status} status and confidence {top.confidence:.2f}."
            )
        return summary

    def _build_readiness(self, data_sources: list[DataSourceStatus]) -> dict[str, str]:
        readiness = {
            "sales_data": "simulated",
            "marketing_data": "simulated",
            "llm_reasoning": "not_attached",
        }
        for source in data_sources:
            if source.source_type == "sales":
                readiness["sales_data"] = source.status
            elif source.source_type in {"marketing", "content"}:
                readiness["marketing_data"] = source.status
        return readiness

    def _merge_learning_updates(
        self,
        existing: list[LearningUpdate],
        fresh: list[LearningUpdate],
    ) -> list[LearningUpdate]:
        seen = {
            (item.strategy_key, item.updated_at.isoformat(), item.outcome, item.lesson)
            for item in existing
        }
        merged = list(existing)
        for item in fresh:
            marker = (item.strategy_key, item.updated_at.isoformat(), item.outcome, item.lesson)
            if marker not in seen:
                merged.append(item)
                seen.add(marker)
        return merged

    def _recommendation_strategy(
        self,
        recommendations: list[Recommendation],
        recommendation_id: str,
    ) -> str | None:
        recommendation = next((item for item in recommendations if item.recommendation_id == recommendation_id), None)
        return recommendation.strategy_key if recommendation else None

    def _metric_value(self, snapshot: MetricSnapshot, metric_name: str) -> float:
        value = getattr(snapshot, metric_name, None)
        if value is None:
            raise ValueError(f"Unsupported metric {metric_name}")
        return float(value)

    def _consistency_score(self, scores: list[float]) -> float:
        if len(scores) <= 1:
            return 50.0
        average = sum(scores) / len(scores)
        avg_deviation = sum(abs(score - average) for score in scores) / len(scores)
        return max(0.0, min(100.0, 100.0 - avg_deviation))

    def _deserialize_snapshots(self, rows: list[dict]) -> list[MetricSnapshot]:
        return [
            MetricSnapshot(
                captured_at=datetime.fromisoformat(row["captured_at"]),
                revenue=row["revenue"],
                leads=row["leads"],
                conversion_rate=row["conversion_rate"],
                ad_spend=row["ad_spend"],
                content_engagement_rate=row["content_engagement_rate"],
                returning_customer_rate=row["returning_customer_rate"],
                notes=row.get("notes", []),
            )
            for row in rows
        ]

    def _deserialize_recommendations(self, rows: list[dict]) -> list[Recommendation]:
        normalized: list[Recommendation] = []
        for row in rows:
            execution_payload = row.get("execution_plan")
            execution_plan = self._deserialize_execution_plan(execution_payload)
            normalized.append(
                Recommendation(
                    recommendation_id=row["recommendation_id"],
                    strategy_key=row["strategy_key"],
                    category=row["category"],
                    title=row.get("title", row.get("objective", row["strategy_key"])),
                    action=row["action"],
                    root_cause=row.get("root_cause", ""),
                    why_this_matters=row.get("why_this_matters", ""),
                    reason=row.get("reason", row.get("reasoning", [])),
                    expected_impact=row.get("expected_impact", row.get("expected_outcome", "")),
                    expected_metric=row.get("expected_metric", "revenue"),
                    expected_value=row.get("expected_value", 0.0),
                    confidence=row["confidence"],
                    priority=row["priority"],
                    strategy_status=row.get("strategy_status", "test"),
                    execution_plan=execution_plan,
                    requires_validation=row.get("requires_validation", False),
                )
            )
        return normalized

    def _deserialize_execution_plan(self, payload: dict | None) -> ExecutionPlan:
        if not payload:
            return ExecutionPlan(
                objective="No execution plan stored.",
                weekly_plan=WeeklyPlan(posts_per_week=0, platforms=[], frequency="Not set"),
                content_strategy=[],
                content_ideas=[],
                hooks=[],
                posting_schedule=PostingSchedule(best_times=[], frequency="Not set"),
                experiment_plan=[],
                paid_strategy=[],
                success_metrics=[],
            )

        weekly = payload.get("weekly_plan", {})
        schedule = payload.get("posting_schedule", {})
        return ExecutionPlan(
            objective=payload.get("objective", ""),
            weekly_plan=WeeklyPlan(
                posts_per_week=weekly.get("posts_per_week", 0),
                platforms=weekly.get("platforms", []),
                frequency=weekly.get("frequency", "Not set"),
            ),
            content_strategy=payload.get("content_strategy", []),
            content_ideas=[
                PlannedContentIdea(
                    title=item.get("title", ""),
                    concept=item.get("concept", ""),
                )
                for item in payload.get("content_ideas", [])
            ],
            hooks=payload.get("hooks", []),
            posting_schedule=PostingSchedule(
                best_times=schedule.get("best_times", []),
                frequency=schedule.get("frequency", "Not set"),
            ),
            experiment_plan=[
                ExperimentStep(
                    test_name=item.get("test_name", ""),
                    variable_to_change=item.get("variable_to_change", ""),
                    success_signal=item.get("success_signal", ""),
                )
                for item in payload.get("experiment_plan", [])
            ],
            paid_strategy=payload.get("paid_strategy", []),
            success_metrics=[
                SuccessMetric(
                    metric=item.get("metric", ""),
                    target=item.get("target", ""),
                    why_it_matters=item.get("why_it_matters", ""),
                )
                for item in payload.get("success_metrics", [])
            ],
        )

    def _deserialize_outcomes(self, rows: list[dict]) -> list[RecommendationOutcome]:
        return [
            RecommendationOutcome(
                recommendation_id=row["recommendation_id"],
                measured_at=datetime.fromisoformat(row["measured_at"]),
                expected_metric=row.get("expected_metric", "revenue"),
                expected_value=row.get("expected_value", 0.0),
                actual_value=row.get("actual_value", 0.0),
                performance_delta=row.get("performance_delta", 0.0),
                classification=row.get("classification", "mixed"),
                performance_score=row.get("performance_score", row.get("outcome_score", 0.5) * 100),
                confidence_adjustment=row.get("confidence_adjustment", 0.0),
                stability=row.get("stability", 50.0),
                risk_level=row.get("risk_level", "medium"),
                strategy_update=row.get("strategy_update", "test"),
                actual_result=row["actual_result"],
                outcome_score=row["outcome_score"],
                summary=row["summary"],
            )
            for row in rows
        ]

    def _deserialize_learning_updates(self, rows: list[dict]) -> list[LearningUpdate]:
        return [
            LearningUpdate(
                strategy_key=row["strategy_key"],
                outcome=row["outcome"],
                what_worked=row.get("what_worked", ""),
                what_failed=row.get("what_failed", ""),
                scale_next=row.get("scale_next", ""),
                pause_next=row.get("pause_next", ""),
                test_next=row.get("test_next", ""),
                lesson=row["lesson"],
                evidence=row["evidence"],
                confidence=row["confidence"],
                adjustment=row["adjustment"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def _build_trend_summary(self, snapshots: list[MetricSnapshot]) -> dict[str, str]:
        if len(snapshots) < 2:
            return {"status": "baseline_only"}

        previous = snapshots[-2]
        current = snapshots[-1]
        return {
            "revenue": self._trend_label(previous.revenue, current.revenue),
            "leads": self._trend_label(previous.leads, current.leads),
            "conversion_rate": self._trend_label(previous.conversion_rate, current.conversion_rate),
            "content_engagement_rate": self._trend_label(
                previous.content_engagement_rate,
                current.content_engagement_rate,
            ),
            "returning_customer_rate": self._trend_label(
                previous.returning_customer_rate,
                current.returning_customer_rate,
            ),
        }

    def _content_types_for_strategy(self, strategy_key: str) -> list[str]:
        mapping = {
            "scale_winning_content": ["short-form video", "hook-led creative"],
            "repair_conversion_path": ["offer clarity page", "objection handling content"],
            "push_retention_program": ["email retention flow", "customer education"],
            "controlled_growth_experiment": ["variant test creative"],
        }
        return mapping.get(strategy_key, ["problem-solution content"])

    def _pct_change(self, previous: float, current: float) -> float:
        if previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100

    def _trend_label(self, previous: float, current: float) -> str:
        delta = self._pct_change(previous, current)
        if delta > 5:
            return "up"
        if delta < -5:
            return "down"
        return "stable"
