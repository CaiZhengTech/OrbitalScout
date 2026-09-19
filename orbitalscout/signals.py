"""The signals. Six functions, one signature, and a list. SPEC Section 7.

Only S1 is registered. A signal joins SIGNALS when it has been measured to
improve lift over the B1b null, per the admission rule in CLAUDE.md, and its
null result is recorded if it does not.

Signature, per SPEC Section 7 and CLAUDE.md:

    score(zone_features: pd.DataFrame, context) -> pd.Series

SPEC Section 7 describes the result as one score per zone-date. Step 2
established zone-year-bin as the grain of a residual, and the rung 1 feature is
one row per zone-year, so the contract here is one score per **row of the input
frame**. Later signals that genuinely need a per-date grain, S2 spatial and S5
persistence, are handed a per-date frame and the signature still holds.

Every signal returns a score where **larger means more urgent to visit**, so
ranking is always a descending sort and no signal needs a special branch.
"""

import numpy as np
import pandas as pd

from . import config, rank
from .ingest import melt


def s1_temporal_anomaly(zone_features, context=None):
    """How far a zone sits below its own phenology-aligned history.

    The feature column is the within-field relative residual from Step 2:
    negative when a zone is doing worse than its own normal. Urgency is the
    negation of it, so that larger is more urgent.

    A missing residual stays missing. Scoring it zero would place a zone whose
    standing is unknown exactly at its own average, which is a claim the data
    does not support.

    `context` is unused by S1 and accepted so every signal shares one signature.
    """
    return -zone_features["feature_ndvi"]


SIGNALS = (s1_temporal_anomaly,)


# Grid neighbours are arithmetic on the packed zone id: east and west shift by
# the stride, north and south by one. No spatial join, no geometry library.
NEIGHBOUR_OFFSETS = tuple(
    dcol * melt._STRIDE + drow
    for dcol in (-1, 0, 1) for drow in (-1, 0, 1)
    if (dcol, drow) != (0, 0)
)


def neighbour_mean(zone_years, value_column, min_neighbours=config.MIN_NEIGHBOURS):
    """Mean of the eight surrounding cells, within the same field-year.

    Looked up under the **target's own field id**, so a neighbouring cell that
    belongs to a different field simply does not match. That is not a tidiness
    rule: the next field over is a different crop on a different planting date,
    and comparing across it would undo the within-field framing the whole
    project rests on.

    A zone is never its own neighbour. Including itself would pull the
    neighbourhood toward the very anomaly being measured and shrink it.

    Fewer than `min_neighbours` present and the result is null, because a mean
    over one or two zones is not a local expectation. Same floor and the same
    reasoning as `MIN_PRIOR_YEARS`.
    """
    key = [zone_years["field_id"], zone_years["year"], zone_years["zone_id"]]
    values = pd.Series(
        zone_years[value_column].to_numpy(),
        index=pd.MultiIndex.from_arrays(key),
    )
    total = np.zeros(len(zone_years))
    count = np.zeros(len(zone_years), dtype=int)
    for offset in NEIGHBOUR_OFFSETS:
        found = values.reindex(pd.MultiIndex.from_arrays(
            [key[0], key[1], key[2] + offset]
        )).to_numpy()
        present = ~np.isnan(found)
        total[present] += found[present]
        count[present] += 1

    mean = np.divide(total, count, out=np.full(len(zone_years), np.nan),
                     where=count >= int(min_neighbours))
    return pd.Series(mean, index=zone_years.index)


def s2_spatial_anomaly(zone_features, context=None):
    """How far a zone sits below the neighbours it shares a field-year with.

    A **level** signal, deliberately. Subtracting a temporal baseline would make
    this a spatially local restatement of S1 and would lose the thing SPEC
    Section 7 wants from it: a score for a zone with no usable history.

    The cost of that is known in advance and recorded in the Step 5 decision
    record. A level signal partly reproduces the permanent soil map, since a
    patch that is always sandy is always below its neighbours, and removing the
    soil map is what D17 is for. Whether it pays for itself is the admission
    rule's decision, not this function's.

    `neighbour_level` is attached upstream, the way `prior_level` is for B1a,
    because the spatial work is feature assembly rather than scoring.
    """
    return zone_features["neighbour_level"] - zone_features["season_level"]


# NDWI tracks canopy water and NDRE tracks chlorophyll; both are expected to
# move before NDVI, which tracks biomass. SPEC Section 7's mechanism is that
# ordering, so S3 is a directional contrast and not a symmetric spread.
EARLY_INDICES = ("ndre", "ndwi")
LATE_INDEX = "ndvi"


def s3_multi_index_divergence(zone_features, context=None):
    """How much worse the early indices read than NDVI does.

    Large when NDVI still looks acceptable and water or chlorophyll do not,
    which is the "before visible decline" case Section 7 asks for.

    Each index is standardised **within field-year first**. NDWI varies over a
    different range from NDVI, so differencing raw residuals would let the
    wider index decide the contrast on scale alone rather than on disagreement.

    Deliberately blind to level. Three indices that are all equally bad give the
    same contrast as three that are all equally good, because agreement is S1's
    subject and disagreement is this one's. A symmetric measure such as the
    spread of the three was rejected: it would also fire when NDVI is the worst
    of the three, which is not an early warning.

    A zone missing any index is unscored, which needs no guard: a null survives
    the z-score and the mean, so the contrast is null on its own. An explicit
    check here was written first and then deleted, because mutation testing
    showed removing it changed nothing.
    """
    z = {name: rank.zscore_within_field(zone_features, f"feature_{name}")
         for name in (LATE_INDEX,) + EARLY_INDICES}
    early = sum(z[name] for name in EARLY_INDICES) / len(EARLY_INDICES)
    return z[LATE_INDEX] - early


def multi_index_level(zone_features, context=None):
    """Diagnostic, not a signal: all three residuals as one level.

    Not "divergence", so this is not S3 and it is not registered. It exists so
    that a null result on S3 cannot be read as a null result on "NDRE and NDWI
    carry nothing." Step 5, Decision 18, for the same reason B2 reports two
    periods at Step 4.
    """
    names = (LATE_INDEX,) + EARLY_INDICES
    z = [rank.zscore_within_field(zone_features, f"feature_{name}") for name in names]
    return -sum(z) / len(z)
