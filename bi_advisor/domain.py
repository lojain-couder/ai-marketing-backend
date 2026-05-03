from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass
class BusinessProfile:
    business_id: str
    name: str
    industry: str
    audience_type: str
    goals: list[str]
    channels: list[str]
    value_proposition: str = ""
    constraints: list[str] = field(default_factory=list)
    strategic_notes: list[str] = field(default_factory=list)
    learned_preferences: list[str] = field(default_factory=list)


@dataclass
class MetricSnapshot:
    captured_at: datetime
    revenue: float
    leads: int
    conversion_rate: float
    ad_spend: float
    content_engagement_rate: float
    returning_customer_rate: float
    notes: list[str] = field(default_factory=list)


@dataclass
class DataSourceStatus:
    source_name: str
    source_type: str
    status: str
    last_sync_at: datetime | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class StrategyPerformance:
    strategy_key: str
    strategy_label: str = ""
    successes: int = 0
    failures: int = 0
    neutral: int = 0
    average_outcome_score: float = 0.5
    last_outcome_score: float = 0.5
    last_summary: str = ""
    recommended_posture: str = "test"
    confidence_history: list[float] = field(default_factory=list)
    recommended_channels: list[str] = field(default_factory=list)
    recommended_content_types: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    average_performance_score: float = 50.0
    consistency_score: float = 50.0
    total_runs: int = 0


@dataclass
class BehavioralProfile:
    business_id: str
    preferred_growth_levers: list[str] = field(default_factory=list)
    winning_patterns: list[str] = field(default_factory=list)
    weak_patterns: list[str] = field(default_factory=list)
    risky_patterns: list[str] = field(default_factory=list)
    recommended_channels: list[str] = field(default_factory=list)
    recommended_content_types: list[str] = field(default_factory=list)
    decision_warnings: list[str] = field(default_factory=list)
    trend_summary: dict[str, str] = field(default_factory=dict)
    strategy_performance: list[StrategyPerformance] = field(default_factory=list)
    last_updated: datetime | None = None


@dataclass
class Insight:
    title: str
    summary: str
    evidence: list[str]
    impact: str
    reasoning: str


@dataclass
class ContentIdea:
    title: str
    angle: str
    channel: str
    rationale: str
    linked_strategy: str


@dataclass
class PlannedContentIdea:
    title: str
    concept: str


@dataclass
class WeeklyPlan:
    posts_per_week: int
    platforms: list[str]
    frequency: str


@dataclass
class PostingSchedule:
    best_times: list[str]
    frequency: str


@dataclass
class ExperimentStep:
    test_name: str
    variable_to_change: str
    success_signal: str


@dataclass
class SuccessMetric:
    metric: str
    target: str
    why_it_matters: str


@dataclass
class ExecutionPlan:
    objective: str
    weekly_plan: WeeklyPlan
    content_strategy: list[str]
    content_ideas: list[PlannedContentIdea]
    hooks: list[str]
    posting_schedule: PostingSchedule
    experiment_plan: list[ExperimentStep]
    paid_strategy: list[str]
    success_metrics: list[SuccessMetric]


@dataclass
class Recommendation:
    recommendation_id: str
    strategy_key: str
    category: str
    title: str
    action: str
    root_cause: str
    why_this_matters: str
    reason: list[str]
    expected_impact: str
    expected_metric: str
    expected_value: float
    confidence: float
    priority: str
    strategy_status: str
    execution_plan: ExecutionPlan
    requires_validation: bool = False

    @classmethod
    def create(
        cls,
        strategy_key: str,
        category: str,
        title: str,
        action: str,
        root_cause: str,
        why_this_matters: str,
        reason: list[str],
        expected_impact: str,
        expected_metric: str,
        expected_value: float,
        confidence: float,
        priority: str,
        strategy_status: str,
        execution_plan: ExecutionPlan,
        requires_validation: bool = False,
    ) -> "Recommendation":
        return cls(
            recommendation_id=str(uuid.uuid4()),
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


@dataclass
class StrategyEvaluation:
    expected_value: float
    actual_value: float
    performance_delta: float
    classification: str
    performance_score: float
    confidence_adjustment: float
    stability: float
    risk_level: str
    strategy_update: str
    reasoning: str


@dataclass
class RecommendationOutcome:
    recommendation_id: str
    measured_at: datetime
    expected_metric: str
    expected_value: float
    actual_value: float
    performance_delta: float
    classification: str
    performance_score: float
    confidence_adjustment: float
    stability: float
    risk_level: str
    strategy_update: str
    actual_result: str
    outcome_score: float
    summary: str


@dataclass
class LearningUpdate:
    strategy_key: str
    outcome: str
    what_worked: str
    what_failed: str
    scale_next: str
    pause_next: str
    test_next: str
    lesson: str
    evidence: str
    confidence: float
    adjustment: str
    updated_at: datetime


@dataclass
class BusinessStateSummary:
    latest_snapshot_at: datetime | None
    total_snapshots: int
    total_recommendations: int
    total_outcomes: int
    readiness: dict[str, str]
    behavioral_profile: BehavioralProfile


@dataclass
class AdvisorOutput:
    business_id: str
    generated_at: datetime
    state_summary: BusinessStateSummary
    data_backed_insights: list[Insight]
    recommendations: list[Recommendation]
    content_ideas: list[ContentIdea]
    learning_updates: list[LearningUpdate]
    reasoning_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
