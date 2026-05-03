from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .domain import (
    BehavioralProfile,
    BusinessProfile,
    DataSourceStatus,
    LearningUpdate,
    MetricSnapshot,
    Recommendation,
    RecommendationOutcome,
    StrategyPerformance,
)


class BusinessMemoryStore(Protocol):
    def load_business_context(self, business_id: str) -> dict[str, Any]:
        ...

    def save_business_context(
        self,
        profile: BusinessProfile,
        snapshots: list[MetricSnapshot],
        recommendations: list[Recommendation],
        outcomes: list[RecommendationOutcome],
        learning_updates: list[LearningUpdate],
        behavioral_profile: BehavioralProfile,
        data_sources: list[DataSourceStatus],
    ) -> None:
        ...


class FileBusinessMemoryStore:
    """Simple JSON-backed memory store, partitioned by business."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load_business_context(self, business_id: str) -> dict[str, Any]:
        path = self.root / f"{business_id}.json"
        if not path.exists():
            return {
                "profile": None,
                "snapshots": [],
                "recommendations": [],
                "outcomes": [],
                "learning_updates": [],
                "behavioral_profile": None,
                "data_sources": [],
            }

        return json.loads(path.read_text())

    def save_business_context(
        self,
        profile: BusinessProfile,
        snapshots: list[MetricSnapshot],
        recommendations: list[Recommendation],
        outcomes: list[RecommendationOutcome],
        learning_updates: list[LearningUpdate],
        behavioral_profile: BehavioralProfile,
        data_sources: list[DataSourceStatus],
    ) -> None:
        path = self.root / f"{profile.business_id}.json"
        payload = {
            "profile": asdict(profile),
            "snapshots": [self._serialize_dataclass(snapshot) for snapshot in snapshots],
            "recommendations": [self._serialize_dataclass(item) for item in recommendations],
            "outcomes": [self._serialize_dataclass(item) for item in outcomes],
            "learning_updates": [self._serialize_dataclass(item) for item in learning_updates],
            "behavioral_profile": self._serialize_dataclass(behavioral_profile),
            "data_sources": [self._serialize_dataclass(item) for item in data_sources],
        }
        path.write_text(json.dumps(payload, indent=2, default=self._json_default))

    def _serialize_dataclass(self, item: Any) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(item), default=self._json_default))

    def _json_default(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported value: {value!r}")


def deserialize_behavioral_profile(payload: dict[str, Any] | None, business_id: str) -> BehavioralProfile:
    if not payload:
        return BehavioralProfile(business_id=business_id)

    strategies = [
        StrategyPerformance(
            strategy_key=row["strategy_key"],
            strategy_label=row.get("strategy_label", row["strategy_key"]),
            successes=row.get("successes", 0),
            failures=row.get("failures", 0),
            neutral=row.get("neutral", 0),
            average_outcome_score=row.get("average_outcome_score", 0.5),
            last_outcome_score=row.get("last_outcome_score", 0.5),
            last_summary=row.get("last_summary", ""),
            recommended_posture=row.get("recommended_posture", "test"),
            confidence_history=row.get("confidence_history", []),
            recommended_channels=row.get("recommended_channels", []),
            recommended_content_types=row.get("recommended_content_types", []),
        )
        for row in payload.get("strategy_performance", [])
    ]
    last_updated = payload.get("last_updated")
    return BehavioralProfile(
        business_id=payload.get("business_id", business_id),
        preferred_growth_levers=payload.get("preferred_growth_levers", []),
        winning_patterns=payload.get("winning_patterns", []),
        weak_patterns=payload.get("weak_patterns", []),
        risky_patterns=payload.get("risky_patterns", []),
        recommended_channels=payload.get("recommended_channels", []),
        recommended_content_types=payload.get("recommended_content_types", []),
        decision_warnings=payload.get("decision_warnings", []),
        trend_summary=payload.get("trend_summary", {}),
        strategy_performance=strategies,
        last_updated=datetime.fromisoformat(last_updated) if last_updated else None,
    )


def deserialize_data_sources(rows: list[dict[str, Any]]) -> list[DataSourceStatus]:
    sources: list[DataSourceStatus] = []
    for row in rows:
        last_sync_at = row.get("last_sync_at")
        sources.append(
            DataSourceStatus(
                source_name=row["source_name"],
                source_type=row["source_type"],
                status=row["status"],
                last_sync_at=datetime.fromisoformat(last_sync_at) if last_sync_at else None,
                notes=row.get("notes", []),
            )
        )
    return sources
