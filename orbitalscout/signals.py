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
