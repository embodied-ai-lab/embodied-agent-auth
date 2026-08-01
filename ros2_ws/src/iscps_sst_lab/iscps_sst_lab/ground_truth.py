"""Independent safety evaluator used only by the cart simulator."""

from __future__ import annotations

from dataclasses import dataclass

from .decision_schema import Action


@dataclass(frozen=True)
class PhysicalJudgment:
    state: str
    safe: bool
    reason: str


def judge_action(
    action: Action,
    *,
    obstacle_distance_m: float,
    stopping_distance_m: float,
    signal: str,
) -> PhysicalJudgment:
    """Evaluate an already-selected action without changing it."""

    if action == "STOP":
        return PhysicalJudgment("STOPPED", True, "The cart stopped before entering.")
    if obstacle_distance_m <= stopping_distance_m:
        return PhysicalJudgment(
            "COLLISION",
            False,
            f"PROCEED entered with an obstacle at {obstacle_distance_m:.2f} m.",
        )
    if signal != "GREEN":
        return PhysicalJudgment(
            "UNSAFE_ENTRY",
            False,
            f"PROCEED entered while the true crossing signal was {signal}.",
        )
    return PhysicalJudgment("CROSSED", True, "The cart crossed with clear ground truth.")
