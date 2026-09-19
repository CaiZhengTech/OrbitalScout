"""Ground truth. SPEC Section 10.

Primary label: the end-of-season **residual** falls in the bottom decile within
its field-year, against the leave-one-year-out baseline.
Secondary label: the end-of-season **level** falls in the bottom decile within
its field-year, with no baseline subtracted.

Both are the same operation on a different column, so there is one function.
The gap between the two is the thesis of the project, stated as a measurement:
B2 k-means is expected to do well on the level and poorly on the residual.

This is a ranking-quality label, not an incidence label. It answers "under a
fixed scouting budget, can the ranker find the worst zones in this field-year,"
not "how often does something go wrong."
"""

import numpy as np

from . import config

KEYS = ["field_id", "year"]


def bottom_fraction(zone_years, value_column, fraction=config.LABEL_FRACTION):
    """Mark the bottom `fraction` of each field-year. Adds `is_positive`.

    Within field-year, because a farmer walks one field and the question is
    which zones in *this* field to visit. Pooling across fields would let a
    field on generally poor ground donate every positive to a better one, and
    would make the label incomparable to a ranking that is itself within field.

    The positive count rounds **up**. `floor(0.10n)` is zero for every
    field-year under ten zones, which would leave precision undefined there
    rather than measured. Rounding up is why the base rate is 10% only in the
    limit, and why `base_rate` below exists.

    Ties break on `zone_id`, so a field-year whose zones all read the same gets
    an arbitrary but reproducible decile rather than a different one each run.
    """
    if zone_years[value_column].isna().any():
        raise ValueError(
            f"{value_column} has missing values; a zone-year with no measurement "
            "has no label, and counting it as a negative would inflate precision"
        )

    order = zone_years.sort_values(KEYS + [value_column, "zone_id"])
    grouped = order.groupby(KEYS, sort=False)
    rank = grouped.cumcount() + 1
    n = grouped[value_column].transform("size")
    order["is_positive"] = rank <= np.ceil(fraction * n)
    return order.loc[zone_years.index]


def base_rate(marked):
    """The realised positive rate per field-year, indexed by field and year.

    Measured rather than assumed to be `LABEL_FRACTION`. SPEC Section 10 lists
    this among the metrics for exactly this reason: `ceil` pushes small
    field-years well above the decile, an eleven-zone field-year reaching
    18.2%, and a lift quoted against an assumed 0.10 would overstate it.
    """
    return marked.groupby(KEYS)["is_positive"].mean()
