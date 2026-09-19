"""Tests for the primary and secondary labels. SPEC Section 10, Ground truth.

A zone-year is underperforming when it falls in the bottom decile within its
own field-year. Two things about that are easy to get wrong and silent when
wrong: which rows the decile is taken over, and what happens when ten does not
divide the field.
"""

import pandas as pd
import pytest

from orbitalscout import config, label


def frame(sizes, values=None):
    """One field-year per key, with `n` zones carrying values 0, 1, 2, ...

    Ascending values mean zone 0 is the worst, so the bottom decile is the
    lowest-numbered zones and the expected answer is readable by eye.
    """
    rows = []
    for (field_id, year), n in sizes.items():
        vals = values[(field_id, year)] if values else range(n)
        rows += [(f"f{field_id}z{i}", field_id, year, float(v))
                 for i, v in enumerate(vals)]
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "value"])


def positives(marked):
    return sorted(marked.loc[marked["is_positive"], "zone_id"])


def test_the_decile_is_taken_within_each_field_year_separately():
    """Pooling would let a poor field donate every positive to a good one."""
    poor = [0.0] * 20
    good = [1.0] * 20
    marked = label.bottom_fraction(frame({(1, 2024): 20, (2, 2024): 20},
                                         {(1, 2024): poor, (2, 2024): good}),
                                   "value")
    by_field = marked[marked["is_positive"]].groupby("field_id").size()
    assert by_field.to_dict() == {1: 2, 2: 2}, "the decile was pooled across fields"


def test_the_same_field_is_labelled_separately_in_each_year():
    marked = label.bottom_fraction(frame({(1, 2023): 20, (1, 2024): 20}), "value")
    by_year = marked[marked["is_positive"]].groupby("year").size()
    assert by_year.to_dict() == {2023: 2, 2024: 2}


def test_the_positive_count_rounds_up_so_small_fields_are_labelled():
    """floor(0.10n) is zero for every field-year under ten zones.

    Those field-years would then have no positives at all and precision would
    be undefined there rather than measured.
    """
    marked = label.bottom_fraction(frame({(1, 2024): 5}), "value")
    assert positives(marked) == ["f1z0"], "a five-zone field-year lost its label"


def test_the_base_rate_is_not_ten_percent_when_ten_does_not_divide_the_field():
    """Step 4, Decision 10. The construction fixes 10% only in the limit.

    Eleven zones give ceil(1.1) = 2 positives, an 18.2% base rate. Reporting a
    lift over an assumed 0.10 would overstate it by nearly a factor of two.
    """
    marked = label.bottom_fraction(frame({(1, 2024): 11}), "value")
    rates = label.base_rate(marked)
    assert rates.loc[(1, 2024)] == pytest.approx(2 / 11)
    assert rates.loc[(1, 2024)] != pytest.approx(0.10)


def test_ties_break_on_zone_id_so_two_runs_agree():
    """With every value equal the decile is arbitrary, so it must be fixed."""
    flat = {(1, 2024): [0.5] * 20}
    first = label.bottom_fraction(frame({(1, 2024): 20}, flat), "value")
    shuffled = frame({(1, 2024): 20}, flat).sample(frac=1, random_state=7)
    second = label.bottom_fraction(shuffled, "value")
    assert positives(first) == positives(second) == ["f1z0", "f1z1"]


def test_the_lowest_values_are_the_positives_not_the_highest():
    """Underperforming means low. A sign flip would invert every result."""
    marked = label.bottom_fraction(frame({(1, 2024): 10}), "value")
    assert positives(marked) == ["f1z0"]


def test_a_missing_value_raises_rather_than_counting_as_a_negative():
    """Silently treating an unmeasured zone as healthy inflates precision."""
    f = frame({(1, 2024): 10})
    f.loc[3, "value"] = None
    with pytest.raises(ValueError, match="missing"):
        label.bottom_fraction(f, "value")


def test_the_label_fraction_is_the_decile_the_spec_fixed():
    assert config.LABEL_FRACTION == 0.10
