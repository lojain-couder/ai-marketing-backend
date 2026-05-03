from __future__ import annotations

from .domain import Recommendation, StrategyEvaluation


class StrategyEvaluationEngine:
    """Turn expected vs actual performance into decision-ready signals."""

    def evaluate(
        self,
        recommendation: Recommendation,
        actual_value: float,
        historical_scores: list[float],
    ) -> StrategyEvaluation:
        expected_value = recommendation.expected_value
        performance_delta = self._performance_delta(expected_value, actual_value)
        stability = self._stability_score(historical_scores)
        classification = self._classify(performance_delta, stability)
        performance_score = self._performance_score(performance_delta, classification)
        confidence_adjustment = self._confidence_adjustment(classification, stability)
        risk_level = self._risk_level(classification, stability, historical_scores)
        strategy_update = self._strategy_update(classification, stability, historical_scores)
        reasoning = self._reasoning(
            recommendation=recommendation,
            performance_delta=performance_delta,
            classification=classification,
            stability=stability,
            risk_level=risk_level,
            strategy_update=strategy_update,
        )

        return StrategyEvaluation(
            expected_value=expected_value,
            actual_value=actual_value,
            performance_delta=performance_delta,
            classification=classification,
            performance_score=performance_score,
            confidence_adjustment=confidence_adjustment,
            stability=stability,
            risk_level=risk_level,
            strategy_update=strategy_update,
            reasoning=reasoning,
        )

    def _performance_delta(self, expected_value: float, actual_value: float) -> float:
        if expected_value == 0:
            return 0.0
        return ((actual_value - expected_value) / expected_value) * 100

    def _classify(self, performance_delta: float, stability: float) -> str:
        if performance_delta >= 15:
            return "success"
        if performance_delta >= 0:
            return "moderate_success"
        if performance_delta > -10 or stability < 45:
            return "mixed"
        return "failure"

    def _performance_score(self, performance_delta: float, classification: str) -> float:
        if classification == "success":
            return min(100.0, 85.0 + min(15.0, performance_delta * 0.5))
        if classification == "moderate_success":
            return min(84.0, 65.0 + max(0.0, performance_delta))
        if classification == "mixed":
            return max(40.0, 55.0 + performance_delta)
        return max(0.0, 35.0 + performance_delta)

    def _confidence_adjustment(self, classification: str, stability: float) -> float:
        stability_factor = (stability - 50.0) / 100.0
        if classification == "success":
            return round(0.12 + max(0.0, stability_factor), 3)
        if classification == "moderate_success":
            return round(0.05 + max(0.0, stability_factor / 2), 3)
        if classification == "mixed":
            return round(-0.02 if stability < 50 else 0.0, 3)
        return round(-0.12 - max(0.0, (50.0 - stability) / 100.0), 3)

    def _stability_score(self, historical_scores: list[float]) -> float:
        if len(historical_scores) <= 1:
            return 50.0
        average = sum(historical_scores) / len(historical_scores)
        average_deviation = sum(abs(score - average) for score in historical_scores) / len(historical_scores)
        return max(0.0, min(100.0, 100.0 - average_deviation))

    def _risk_level(
        self,
        classification: str,
        stability: float,
        historical_scores: list[float],
    ) -> str:
        recent_failures = len([score for score in historical_scores[-3:] if score < 40])
        if classification == "failure" or recent_failures >= 2 or stability < 35:
            return "high"
        if classification == "mixed" or stability < 60:
            return "medium"
        return "low"

    def _strategy_update(
        self,
        classification: str,
        stability: float,
        historical_scores: list[float],
    ) -> str:
        if classification == "success" and stability >= 60:
            return "scale"
        if classification == "moderate_success":
            return "monitor"
        if classification == "mixed":
            return "test"
        recent_failures = len([score for score in historical_scores[-3:] if score < 40])
        if recent_failures >= 2:
            return "avoid"
        return "avoid" if classification == "failure" else "test"

    def _reasoning(
        self,
        recommendation: Recommendation,
        performance_delta: float,
        classification: str,
        stability: float,
        risk_level: str,
        strategy_update: str,
    ) -> str:
        return (
            f"{recommendation.title} was evaluated on {recommendation.expected_metric}. "
            f"Actual performance was {performance_delta:.1f}% versus expected, "
            f"which classifies as {classification}. Stability is {stability:.1f}, "
            f"so risk is {risk_level} and the strategy should be treated as {strategy_update}."
        )
