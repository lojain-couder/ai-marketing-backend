from __future__ import annotations

from typing import Protocol

from .domain import AdvisorOutput, BusinessProfile, DataSourceStatus, MetricSnapshot


class SalesDataProvider(Protocol):
    def fetch_sales_snapshot(self, profile: BusinessProfile) -> MetricSnapshot:
        ...


class MarketingDataProvider(Protocol):
    def fetch_data_sources(self, profile: BusinessProfile) -> list[DataSourceStatus]:
        ...


class AdvisorReasoningLayer(Protocol):
    def refine_output(self, profile: BusinessProfile, advisor_output: AdvisorOutput) -> AdvisorOutput:
        ...
