"""Governance risk score (proposal RS-08).

A transparent weighted sum, stored with its full breakdown. No model is involved: a
priority number a reviewer cannot interrogate gets ignored within a fortnight, and an
unexplainable one is worse than none at all.

Every component is normalised to 0..1 and multiplied by its weight, so the breakdown
reads directly as "Critical severity contributed 30 of this 78".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import Error

SEVERITY_WEIGHT = {"Critical": 1.0, "High": 0.7, "Medium": 0.4, "Low": 0.15}

RECURRENCE_BAND_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.55, "LOW": 0.15}

WEIGHTS = {
    "severity": 0.30,
    "sla_pressure": 0.25,
    "recurrence": 0.20,
    "rebuttal_open": 0.10,
    "business_impact": 0.10,
    "age_decay": 0.05,
}

# Beyond this an error is considered maximally aged for scoring purposes; without a cap a
# single forgotten item from last year would dominate the whole queue forever.
AGE_SATURATION_DAYS = 30.0


@dataclass
class RiskComponent:
    name: str
    weight: float
    value: float          # normalised 0..1
    contribution: float   # weight * value * 100


def compute_risk(
    error: Error,
    *,
    sla_ratio: float = 0.0,
    recurrence_band: str | None = None,
    has_open_rebuttal: bool = False,
    business_impact: float = 0.0,
    now: datetime | None = None,
) -> tuple[float, dict]:
    """Returns (score 0..100, breakdown) — pure, so it is exhaustively unit-testable."""
    now = now or datetime.now(timezone.utc)

    created = error.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_days = ((now - created).total_seconds() / 86400.0) if created else 0.0

    values = {
        "severity": SEVERITY_WEIGHT.get(error.severity, 0.4),
        # Consumption is allowed past 1.0 (a breach keeps getting worse) but saturates at
        # 1.5x so a very old breach cannot crowd out everything else in the queue.
        "sla_pressure": min(max(sla_ratio, 0.0), 1.5) / 1.5,
        "recurrence": RECURRENCE_BAND_WEIGHT.get(recurrence_band or "", 0.0),
        "rebuttal_open": 1.0 if has_open_rebuttal else 0.0,
        "business_impact": min(max(business_impact, 0.0), 1.0),
        "age_decay": min(max(age_days, 0.0) / AGE_SATURATION_DAYS, 1.0),
    }

    components = [
        RiskComponent(name, WEIGHTS[name], v, round(WEIGHTS[name] * v * 100, 2))
        for name, v in values.items()
    ]
    score = round(sum(c.contribution for c in components), 2)

    return score, {
        "score": score,
        "computed_at": now.isoformat(),
        "components": [
            {"name": c.name, "weight": c.weight, "value": round(c.value, 4),
             "contribution": c.contribution}
            for c in components
        ],
    }
