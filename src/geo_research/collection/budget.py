"""Explicit collection budget and unknown-cost policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UnknownCostPolicy = Literal["block", "allow"]


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    per_request_usd: float | None = None
    per_target_usd: float | None = None
    per_engine_usd: float | None = None
    per_platform_usd: float | None = None
    per_run_usd: float | None = None
    daily_usd: float | None = None
    unknown_cost_policy: UnknownCostPolicy = "block"
    cli_max_cost_usd: float | None = None


class BudgetTracker:
    """Authorizes estimates and records actual costs separately from estimates."""

    def __init__(self, policy: BudgetPolicy) -> None:
        self.policy = policy
        self.total_estimated_usd = 0.0
        self.total_actual_usd = 0.0
        self._target_estimates: dict[str, float] = {}

    def authorize(
        self, target_id: str, target_dimension: str, estimate: float | None
    ) -> bool:
        """Approve a request only when its known estimate fits every applicable cap."""
        if estimate is None:
            return self.policy.unknown_cost_policy == "allow"
        caps = (self.policy.per_request_usd, self.policy.cli_max_cost_usd)
        if any(cap is not None and estimate > cap for cap in caps):
            return False
        if (
            self.policy.per_run_usd is not None
            and self.total_estimated_usd + estimate > self.policy.per_run_usd
        ):
            return False
        current_target = self._target_estimates.get(target_id, 0.0)
        target_cap = self.policy.per_target_usd
        if target_cap is not None and current_target + estimate > target_cap:
            return False
        dimension_cap = self.policy.per_engine_usd or self.policy.per_platform_usd
        if dimension_cap is not None and current_target + estimate > dimension_cap:
            return False
        self.total_estimated_usd += estimate
        self._target_estimates[target_id] = current_target + estimate
        return True

    def record_actual_cost(self, actual_cost: float | None) -> None:
        """Record actual cost without coercing an unknown value to zero."""
        if actual_cost is not None:
            self.total_actual_usd += actual_cost
