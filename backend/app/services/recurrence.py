"""Recurrence risk scoring (proposal QS-01).

The counting rule: every number here is computed from facts supplied by SQL. A language
model never counts, never scores, and never sets the band — it is given the output of
this function and writes prose around it. A model that counts will eventually miscount,
and a governance product that quotes a hallucinated figure in a leadership pack is
finished, not degraded.

Pure function of its inputs, so it is exhaustively testable without a database, a network
call, or a model.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_WEIGHT = {"Critical": 1.0, "High": 0.75, "Medium": 0.45, "Low": 0.2}

WEIGHTS = {
    "similar_volume": 0.30,
    "process_concentration": 0.25,
    "trend": 0.20,
    "severity": 0.15,
    "prior_capa_ineffective": 0.10,
}

# Twenty similar findings in 90 days is already maximal evidence of recurrence; counting
# higher adds no information and would let one pathological cluster swamp the scale.
SIMILAR_VOLUME_CAP = 20
# A 50% quarter-on-quarter rise is treated as the top of the scale.
TREND_SATURATION_PCT = 50.0

BAND_HIGH = 65.0
BAND_MEDIUM = 30.0

# Retrieval thresholds. Anything beyond the ceiling is not a neighbour; anything inside
# the floor is the same incident filed twice, which is a duplicate, not a recurrence.
#
# A threshold belongs to an embedding space, not to the product. `text-embedding-3-small`
# places genuine paraphrases around 0.15-0.25; the offline lexical embedder has no
# semantic generalisation, so the same paraphrases land near 0.6 and a 0.25 ceiling would
# retrieve nothing but near-verbatim repeats. These are calibrated separately, and
# retrieval already refuses to mix models, so the two are never compared.
DISTANCE_CEILING = 0.25
DUPLICATE_FLOOR = 0.05

_OFFLINE_CEILING = 0.62
_OFFLINE_FLOOR = 0.08


def thresholds_for(embedding_model: str | None) -> tuple[float, float]:
    """Returns (ceiling, duplicate_floor) calibrated for the given embedding space."""
    from app.services.embedding_service import is_offline_model

    if is_offline_model(embedding_model):
        return _OFFLINE_CEILING, _OFFLINE_FLOOR
    return DISTANCE_CEILING, DUPLICATE_FLOOR
MIN_NEIGHBOURS_FOR_SIGNAL = 3
MIN_CORPUS_FOR_SIGNAL = 50


@dataclass(frozen=True)
class RecurrenceMetrics:
    """Facts, all computed in SQL. Nothing here is inferred."""

    similar_90d: int = 0
    same_process: int = 0
    same_team: int = 0
    same_category: int = 0
    previous_quarter_count: int = 0
    current_quarter_count: int = 0
    prior_capa_ineffective: bool = False
    nearest_distance: float | None = None

    @property
    def qoq_delta_pct(self) -> float:
        if self.previous_quarter_count == 0:
            # No baseline: a rise from zero is real but unquantifiable as a percentage,
            # so it is reported as the saturation value rather than as infinity.
            return TREND_SATURATION_PCT if self.current_quarter_count > 0 else 0.0
        delta = self.current_quarter_count - self.previous_quarter_count
        return (delta / self.previous_quarter_count) * 100.0

    @property
    def same_process_ratio(self) -> float:
        return self.same_process / self.similar_90d if self.similar_90d else 0.0


def score_recurrence(metrics: RecurrenceMetrics, severity: str) -> tuple[float, str, dict]:
    """Returns (score 0..100, band, breakdown)."""
    values = {
        "similar_volume": min(metrics.similar_90d / SIMILAR_VOLUME_CAP, 1.0),
        "process_concentration": min(max(metrics.same_process_ratio, 0.0), 1.0),
        "trend": min(max(metrics.qoq_delta_pct, 0.0) / TREND_SATURATION_PCT, 1.0),
        "severity": SEVERITY_WEIGHT.get(severity, 0.45),
        # Deliberately weighted out of proportion to its share. A defect recurring after a
        # corrective action was signed off is the strongest evidence of systemic failure
        # any quality system can produce, and it is the signal a human reviewer is least
        # likely to spot unaided.
        "prior_capa_ineffective": 1.0 if metrics.prior_capa_ineffective else 0.0,
    }

    components = [
        {
            "name": name,
            "weight": WEIGHTS[name],
            "value": round(value, 4),
            "contribution": round(WEIGHTS[name] * value * 100, 2),
        }
        for name, value in values.items()
    ]
    score = round(sum(c["contribution"] for c in components), 2)

    if score >= BAND_HIGH:
        band = "HIGH"
    elif score >= BAND_MEDIUM:
        band = "MEDIUM"
    else:
        band = "LOW"

    return score, band, {"score": score, "band": band, "components": components}


# Two findings filed about the same incident are raised within days of each other.
DUPLICATE_WINDOW_DAYS = 3


def contexts_match(
    *,
    category_a: int | None, category_b: int | None,
    department_a: int | None, department_b: int | None,
    process_a: int | None, process_b: int | None,
) -> bool:
    """Do two findings describe the same operational context?

    Category and department must agree — they are always populated, so a mismatch is
    real evidence of a different context.

    Process is treated as three-valued rather than two-valued: NULL means *unknown*, not
    *different*. Records created before the process field existed carry no process, and
    letting NULL != 6 count as a mismatch made those records permanently unmatchable —
    two byte-identical findings raised on the same day by the same team were not
    recognised as duplicates purely because the older one predated the column.

    So an unknown process cannot rule a duplicate out on its own. It cannot rule one in
    either: category, department and the date window still have to hold, and those are
    the checks that stop findings written from a shared template being collapsed together.
    """
    if category_a != category_b or department_a != department_b:
        return False
    if process_a is not None and process_b is not None:
        return process_a == process_b
    return True


def is_probable_duplicate(
    nearest_distance: float | None,
    floor: float = DUPLICATE_FLOOR,
    *,
    same_context: bool = True,
    days_apart: float | None = None,
) -> bool:
    """Is the nearest neighbour the same incident filed twice, rather than a recurrence?

    Text distance alone is not sufficient evidence, and treating it as such is a real
    failure mode: quality teams write findings from shared templates, so two genuinely
    separate breaches of the same control can be nearly identical in wording. Calling
    those a duplicate suppresses exactly the recurrence signal the engine exists to find.

    A duplicate therefore needs corroboration — the same process and department, and a
    discovery date close enough that it plausibly describes one event.
    """
    if nearest_distance is None or nearest_distance >= floor:
        return False
    if not same_context:
        return False
    if days_apart is not None and days_apart > DUPLICATE_WINDOW_DAYS:
        return False
    return True
