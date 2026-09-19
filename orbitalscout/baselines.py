"""What the ranker has to beat. SPEC Section 10, Baselines.

  B1a  level persistence   the zones that have always been worst will be worst again
  B1b  anomaly persistence the zones unusually bad last time this crop grew, again
  B2   NDVI k-means        what commercial platforms ship

Same contract as a signal: one score per row of the input frame, larger meaning
more urgent, so `rank.rank_within_field` treats a baseline and the ranker
identically and neither gets a special branch.

Each of these is given its best honest shot. A null that has been quietly
handicapped proves nothing, and CLAUDE.md pre-commits to reporting a loss
against B1b as the headline finding rather than tuning until it goes away.

One choice here is worth stating, because it is the third time this trap has
come up. B1b persists a **strictly prior** residual, not the leave-one-year-out
residual the label uses. The leave-one-year-out baseline for 2022 includes
2024, so a B1b score for 2024 built on it would have read the year it is
predicting, and would correlate with the label through shared estimation error
rather than through any real persistence. That is open item 10b of the council
review, and it would have made the null look stronger than it is.
"""

import numpy as np
import pandas as pd

KEYS = ["field_id", "year"]


def b1a_level_persistence(zone_years, level_column="prior_level"):
    """Rank by multi-year mean relative index from prior years, ascending.

    `prior_level` is the feature baseline itself: the mean over strictly prior
    years of a zone's within-field relative index. Ranking by it is the claim
    that permanent soil structure repeats, which it largely does, and is why
    this is hard to beat on the secondary label and near chance on the primary.

    A zone with no prior years stays unscored rather than scoring zero, since
    zero would place it exactly at its own average, which nothing supports.
    """
    return -zone_years[level_column]


def prior_same_crop(targets, history, residual_column="residual"):
    """Attach each target's residual from its last prior year under the same crop.

    Same crop rather than simply the prior year, per SPEC Section 10: if a
    zone-by-crop interaction exists, last year's residual is anti-informative
    about a crop-specific recurrence, which would handicap the null twice over.
    Under the rotation measured at Step 0 this is usually two years back.

    `merge_asof` backward keyed by zone and crop, with exact matches disallowed
    so a year can never persist itself. A zone whose crop has not been grown
    before gets NaN, not zero.
    """
    left = targets.sort_values("year", kind="stable")
    right = (history[["zone_id", "year", "cdl_code", residual_column]]
             .sort_values("year", kind="stable")
             .rename(columns={residual_column: "prior_residual"}))
    merged = pd.merge_asof(
        left, right, on="year", by=["zone_id", "cdl_code"],
        direction="backward", allow_exact_matches=False,
    )
    return merged.set_index(left.index).loc[targets.index]


def b1b_anomaly_persistence(zone_years, residual_column="prior_residual"):
    """Rank by the prior same-crop residual, ascending. The headline null."""
    return -zone_years[residual_column]


def kmeans_1d(values, k, max_iter=50):
    """Lloyd's algorithm in one dimension, started from quantiles. Returns labels.

    Written out rather than taking scikit-learn, which would be a large
    dependency for a one-dimensional clustering. Quantile starts make it
    deterministic, which matters because Lloyd's answer depends on where it
    begins and a baseline that moves between runs cannot be reported.

    Empty clusters are dropped rather than re-seeded, so a field with fewer
    distinct readings than `k` simply ends up with fewer clusters. That is the
    honest answer: a three-zone field does not contain seven management zones.
    """
    values = np.asarray(values, dtype=float)
    k = min(int(k), len(values))
    centres = np.unique(np.quantile(values, np.linspace(0, 1, k)))
    for _ in range(max_iter):
        labels = np.abs(values[:, None] - centres[None, :]).argmin(axis=1)
        present = np.unique(labels)
        moved = np.array([values[labels == c].mean() for c in present])
        if len(moved) == len(centres) and np.allclose(moved, centres):
            break
        centres = moved
    return np.abs(values[:, None] - centres[None, :]).argmin(axis=1)


def b2_ndvi_kmeans(zone_years, k, level_column="prior_level"):
    """Cluster each field-year's prior mean index and score by cluster mean.

    Per field-year, because a management zone map is drawn for one field.
    Clustering across fields would drop a whole poor field into one cluster and
    compare it against its neighbours, which is not what the product does.

    Every zone in a cluster gets the same score and therefore ties, which is
    the substance of the comparison: a commercial map hands a scout a handful
    of polygons, not an ordering. Ties resolve on zone id in `rank`, the same
    arbitrary-but-reproducible way a person picks a spot inside a polygon.

    Fit on prior years only, like everything else here, so the commercial
    comparison is held to the same temporal rule as the ranker.
    """
    out = pd.Series(np.nan, index=zone_years.index, dtype=float)
    for _, group in zone_years.groupby(KEYS, sort=False):
        values = group[level_column].dropna()
        if values.empty:
            continue
        labels = kmeans_1d(values.to_numpy(), k)
        centre = values.groupby(labels).mean()
        out.loc[values.index] = centre.reindex(labels).to_numpy()
    return -out
