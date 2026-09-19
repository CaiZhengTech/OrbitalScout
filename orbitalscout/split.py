"""Holdout by year and by field. SPEC Section 10, CLAUDE.md rule 1.

A random split of zones would produce excellent numbers that mean nothing:
adjacent 30m zones share soil, drainage and management, so a zone in the test
set has a near neighbour in the fit set carrying most of its answer.

What this does and does not govern is worth stating, because at Step 4 it is
easy to overclaim. Blocking applies to anything **fit** on data. Taking an
inventory of Step 4, the only fitted object is B2's k-means, and it is fit
within a single field. Nothing pools across fields until rung 2 weights arrive.
So this split is exercised at Step 4 but has nothing to separate yet, and
`RESULTS.md` says so rather than reporting the gate as passed on it.

The per-zone baselines are not fit. They are computed from one zone's own
history under a temporal rule, and that rule is enforced in `baseline.py` and
tested in `tests/test_splits.py`.

**Anything added to the evaluation that is fit across fields must come through
here.** That sentence is the whole enforcement mechanism; there is no registry.
"""

from . import config

N_FIELD_FOLDS = 5


def field_folds(zone_years, n_folds=N_FIELD_FOLDS):
    """Assign each field to a fold, balanced by zone count. Returns field -> fold.

    This is `GroupKFold` grouped by field. Since every group is one field,
    sklearn's version reduces to greedy bin packing: take the largest field
    first and put it in the lightest fold. Written out rather than taking the
    dependency for six lines.

    Balanced by zones rather than by field count because field size spans 1 to
    2,892 zones here. Dealing out equal numbers of fields would leave one fold
    holding several times the data of another.

    Ties on size break on field id so two runs over the same fields agree.
    """
    sizes = zone_years.groupby("field_id").size()
    order = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))
    load = [0] * int(n_folds)
    folds = {}
    for field_id, n in order:
        fold = min(range(int(n_folds)), key=lambda k: (load[k], k))
        folds[field_id] = fold
        load[fold] += n
    return folds


def split(zone_years, test_year, test_fold, folds):
    """The fit and test frames for one (year, field-fold) cell.

    Fit is every row from a year **strictly before** `test_year` whose field is
    not in `test_fold`. Strictly before rather than merely different, because a
    thing fit on 2025 to score 2024 could not have been run in 2024.

    Test is `test_year`, restricted to the fields in `test_fold`. Across the
    folds every field is tested exactly once.
    """
    in_test_fold = zone_years["field_id"].map(folds) == test_fold
    fit = zone_years[(zone_years["year"] < test_year) & ~in_test_fold]
    test = zone_years[(zone_years["year"] == test_year) & in_test_fold]
    return fit.reset_index(drop=True), test.reset_index(drop=True)


def year_folds(held_out=config.HELD_OUT_YEARS):
    """(test_year, fit_years) per held-out season, evaluated separately.

    Reported as a spread across the three seasons rather than a single number,
    so a year that happened to be easy cannot carry the result.
    """
    return tuple((year, tuple(y for y in config.YEARS if y < year)) for year in held_out)


def folds(zone_years, n_folds=N_FIELD_FOLDS, held_out=config.HELD_OUT_YEARS):
    """Every (test_year, test_fold, fit, test) the evaluation runs over."""
    assigned = field_folds(zone_years, n_folds)
    for test_year, _fit_years in year_folds(held_out):
        for test_fold in range(int(n_folds)):
            fit, test = split(zone_years, test_year, test_fold, assigned)
            yield test_year, test_fold, fit, test
