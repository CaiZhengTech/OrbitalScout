"""Ranking metrics. SPEC Section 10, Metrics.

Anything added here that is **fit across fields** must come through
`split.py`. At Step 4 nothing is, because every fitted object is fit within a
single field, but rung 2 pools z-score statistics and that stops being true.

Three things about the reporting are deliberate, and all three exist because
the base rate is fixed by construction rather than observed.

`precision_ceiling` accompanies every precision. A budget larger than the
positive count cannot be spent entirely on positives, so at k = 20% against a
10% base rate a perfect ranker caps at 0.50. Without the ceiling a reader
compares precision@5% against precision@20%, sees a fall, and attributes to
the ranker what is arithmetic.

`base_rate` is measured rather than assumed. The label is the bottom decile
within field-year and the positive count rounds up, so an eleven-zone
field-year carries two positives and an 18.2% base rate. Dividing by a nominal
0.10 would overstate lift by nearly a factor of two.

`lift_over_random` is reported because SPEC Section 10 requires it, in the same
row as the precision it rescales and never as a headline. With the base rate
near constant it is precision times a constant and carries nothing the
precision does not. Every informative comparison here is ranker against
ranker, where the base rate cancels.

Everything is micro-averaged, pooled over selected zone-years rather than
averaged over field-years, so a one-zone field-year does not carry the same
weight as a 2,892-zone one.
"""

import numpy as np

from . import rank

KEYS = ["field_id", "year"]


def strict_subset(zone_years, zones=None, fraction=None):
    """Drop field-years the budget covers in full. Step 4, Decision 10.

    Takes an unranked frame and sizes the budget from field-year counts alone,
    because the evaluated population must be the same for every method. Deriving
    it from a ranking would make the population an output of the thing being
    measured, even though the answer would come out the same.

    Where every zone is selected, precision equals the base rate whatever the
    ranking does: a five-zone field-year under a twenty-zone budget scores the
    same forwards and reversed. Those field-years report on field size, not on
    skill, and they pull the pooled number toward the base rate, which
    understates the ranker.

    Metrics are reported on the full population **and** on this subset, with
    the excluded share stated, so the exclusion is auditable rather than
    asserted. A fractional budget leaves a strict subset for any field-year of
    two zones or more, so this only bites on the absolute budget.
    """
    sizes = zone_years.groupby(KEYS).size()
    budgets = rank.budget_size(zone_years, zones=zones, fraction=fraction)
    keep = sizes.index[budgets < sizes]
    return zone_years[zone_years.set_index(KEYS).index.isin(keep)].reset_index(drop=True)


def metrics(ranked, zones=None, fraction=None, label_column="is_positive"):
    """Precision, its ceiling, recall, false positive rate and lift at one budget.

    `ranked` carries `rank` from `rank.rank_within_field` and a boolean label
    column. The budget comes from `rank.select_budget`, so the ranking and the
    evaluation cannot disagree about what a budget means.
    """
    selected = rank.select_budget(ranked, zones=zones, fraction=fraction)
    sizes = ranked.groupby(KEYS).size()
    positives = ranked.groupby(KEYS)[label_column].sum()
    budgets = selected.groupby(KEYS).size().reindex(sizes.index, fill_value=0)

    n_zones = int(sizes.sum())
    n_positive = int(positives.sum())
    n_selected = int(len(selected))
    true_positives = int(selected[label_column].sum())

    # The most positives a perfect ranker could have found: it cannot visit
    # more bad zones than exist in a field, nor more zones than the budget.
    ceiling_tp = int(np.minimum(budgets, positives).sum())

    base_rate = n_positive / n_zones
    precision = true_positives / n_selected
    ceiling = ceiling_tp / n_selected
    return {
        "n_field_years": int(len(sizes)),
        "n_zones": n_zones,
        "n_selected": n_selected,
        "base_rate": base_rate,
        "precision": precision,
        "precision_ceiling": ceiling,
        "fraction_of_ceiling": precision / ceiling if ceiling else float("nan"),
        "recall": true_positives / n_positive if n_positive else float("nan"),
        "false_positive_rate": (
            (n_selected - true_positives) / (n_zones - n_positive)
            if n_zones > n_positive else float("nan")
        ),
        "lift_over_random": precision / base_rate if base_rate else float("nan"),
        "lift_ceiling": ceiling / base_rate if base_rate else float("nan"),
    }


def lift_over(method, reference):
    """Precision of one method over another at the same budget.

    This is the informative comparison and the one CLAUDE.md makes the
    headline, because the base rate cancels: what is left is a difference in
    ordering rather than a rescaling of a constructed constant.
    """
    return method["precision"] / reference["precision"]
