"""Rank zones within a field-year and apply a scouting budget. SPEC Section 9.

Rung 1 of the complexity ladder: a single signal, sorted. No model, no
training, no weights.

Ranking is per field-year because a farmer walks one field. Ranking across
fields would let a field with generally poor soil absorb the whole budget,
which is the failure D1 exists to prevent, and it would also make the
within-field label incomparable to the ranking scored against it.
"""

import math


def rank_within_field(scored, score_column="score"):
    """Add a 1-based `rank` per field-year, best first.

    Rows without a score are dropped rather than ranked: a zone whose standing
    is unknown has no position, and giving it one would invent a placement.
    Ties break on zone_id so that two runs over the same data agree.
    """
    ranked = scored[scored[score_column].notna()].copy()
    ranked = ranked.sort_values(
        ["field_id", "year", score_column, "zone_id"],
        ascending=[True, True, False, True],
    )
    ranked["rank"] = ranked.groupby(["field_id", "year"]).cumcount() + 1
    return ranked.reset_index(drop=True)


def budget_size(zone_years, zones=None, fraction=None):
    """Zones a budget selects per field-year, without needing a ranking.

    The evaluation has to know which field-years a budget covers in full, and
    that must not depend on how any method happened to rank them. Same rounding
    rule as `select_budget`, and a test pins the two together.
    """
    if (zones is None) == (fraction is None):
        raise ValueError("pass exactly one of zones or fraction")
    sizes = zone_years.groupby(["field_id", "year"]).size()
    if zones is not None:
        return sizes.clip(upper=int(zones))
    return (sizes * float(fraction)).map(math.ceil).clip(lower=1)


def select_budget(ranked, zones=None, fraction=None):
    """The top of each field-year's ranking under a scouting budget.

    `zones` is an absolute number of zones, which is the agronomically
    meaningful budget: a person walks a fixed amount of ground, not a fixed
    share of whatever field they are in. `fraction` is a share of the field,
    which is how the metric is usually quoted and is kept for comparability.

    A fractional budget rounds up, so no field is scored with an empty
    shortlist. A budget larger than the field takes the whole field.
    """
    if (zones is None) == (fraction is None):
        raise ValueError("pass exactly one of zones or fraction")
    if zones is not None:
        return ranked[ranked["rank"] <= int(zones)].reset_index(drop=True)

    sizes = ranked.groupby(["field_id", "year"])["zone_id"].transform("size")
    budget = (sizes * float(fraction)).map(math.ceil).clip(lower=1)
    return ranked[ranked["rank"] <= budget].reset_index(drop=True)
