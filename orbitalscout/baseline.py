"""The within-field relative, phenology-aligned baseline. SPEC Section 8, D17.

    relative_index(i, t, b) = index(i, t, b) - median over zones in f of index(., t, b)
    baseline(i, b)          = mean over prior years of relative_index(i, ., b)
    residual(i, t, b)       = relative_index(i, t, b) - baseline(i, b)

Built as a chain of DuckDB views over the Step 1 tables, so nothing is copied
until a caller writes the final view out. Each view is one step of the formula
above, which keeps every step inspectable on its own.

Expects `zone_obs`, `zones`, `fields` and a `gdd` table (cdl_code, date, gdd)
to already exist on the connection.
"""

from . import config

INDICES = tuple(config.INDICES)


def _create_events(con, events):
    con.execute("CREATE OR REPLACE TABLE known_events (name VARCHAR, start_date VARCHAR, end_date VARCHAR)")
    for name, start, end, _why in events:
        con.execute("INSERT INTO known_events VALUES (?, ?, ?)", [name, start, end])


def build_views(con, width_gdd, min_field_clear_frac, events=config.KNOWN_EVENTS,
                field_stats=None):
    """Create the baseline view chain on `con`.

    width_gdd: phenology bin width.
    min_field_clear_frac: a field-date whose clear share of zones falls below
        this is dropped, because its median describes only the part of the
        field the clouds happened to leave visible.
    events: windows excluded from baseline history but kept as targets.
    field_stats: optional path to precomputed field_date_stats Parquet. The
        field median must be taken over every zone in a field, so a build that
        processes zones in chunks computes it once over all zones and passes it
        here; recomputing per chunk would take the median of a chunk's zones.
    """
    _create_events(con, events)
    crop_columns = ", ".join(f"crop_{year}" for year in config.YEARS)

    # One row per field per year with its crop code. CSB assigns crop at the
    # field-year level, which is what makes D17 definitional here.
    con.execute(f"""
        CREATE OR REPLACE VIEW field_crop AS
        SELECT field_id,
               CAST(replace(crop_col, 'crop_', '') AS INTEGER) AS year,
               cdl_code
        FROM (UNPIVOT fields ON {crop_columns} INTO NAME crop_col VALUE cdl_code)
    """)

    # Attach growth stage. The inner join to gdd drops observations before the
    # planting origin and any zone-year whose crop is outside the registry,
    # since gdd only carries rows for registry crops on or after planting.
    index_cols = ", ".join(f"o.{name}" for name in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW binned_obs AS
        SELECT o.zone_id, o.field_id, o.year, o.date, {index_cols},
               fc.cdl_code, g.gdd,
               CAST(floor(g.gdd / {float(width_gdd)}) AS INTEGER) AS bin
        FROM zone_obs o
        JOIN field_crop fc ON fc.field_id = o.field_id AND fc.year = o.year
        JOIN gdd g ON g.cdl_code = fc.cdl_code AND g.date = o.date
    """)

    # The field centre on each date, and how much of the field it was measured
    # over. Median rather than mean, so an anomaly covering a large share of the
    # field cannot drag the centre toward itself and shrink its own residual.
    medians = ", ".join(f"median({name}) AS med_{name}" for name in INDICES)
    if field_stats is not None:
        con.execute(
            "CREATE OR REPLACE VIEW field_date_stats AS "
            f"SELECT * FROM read_parquet('{field_stats}')"
        )
    else:
        _field_stats_view(con, medians)
    _zone_views(con, min_field_clear_frac)


def _field_stats_view(con, medians):
    con.execute(f"""
        CREATE OR REPLACE VIEW field_date_stats AS
        SELECT b.field_id, b.date, {medians},
               count(*)::DOUBLE / any_value(z.n_zones) AS clear_frac
        FROM binned_obs b
        JOIN (SELECT field_id, count(*) AS n_zones FROM zones GROUP BY field_id) z
          USING (field_id)
        GROUP BY b.field_id, b.date
    """)


def _zone_views(con, min_field_clear_frac):
    first = INDICES[0]
    relatives = ", ".join(f"b.{name} - s.med_{name} AS rel_{name}" for name in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW relative_obs AS
        SELECT b.zone_id, b.field_id, b.year, b.date, b.bin, b.cdl_code, {relatives},
               b.{first} AS level_{first},
               EXISTS (
                   SELECT 1 FROM known_events e
                   WHERE b.date BETWEEN e.start_date AND e.end_date
               ) AS in_event
        FROM binned_obs b
        JOIN field_date_stats s USING (field_id, date)
        WHERE s.clear_frac >= {float(min_field_clear_frac)}
    """)

    # One value per zone-year-bin. The plain mean is the target for that year;
    # the event-filtered mean is what that year contributes to later history.
    aggregates = ", ".join(
        f"avg(rel_{n}) AS rel_{n}, avg(rel_{n}) FILTER (WHERE NOT in_event) AS rel_{n}_clean"
        for n in INDICES
    )
    con.execute(f"""
        CREATE OR REPLACE VIEW zone_year_bin AS
        SELECT zone_id, field_id, year, bin, any_value(cdl_code) AS cdl_code,
               {aggregates}, avg(level_{first}) AS level_{first}, count(*) AS n_obs
        FROM relative_obs
        GROUP BY zone_id, field_id, year, bin
    """)

    # Strictly prior years only: the window ends one row before the current
    # year, so a year can never contribute to its own baseline. Nulls from
    # event-only years are skipped by avg and count.
    windowed = ", ".join(
        f"avg(rel_{n}_clean) OVER prior AS baseline_{n}" for n in INDICES
    )
    residuals = ", ".join(f"rel_{n} - baseline_{n} AS residual_{n}" for n in INDICES)
    rels = ", ".join(f"rel_{n}" for n in INDICES)
    baselines = ", ".join(f"baseline_{n}" for n in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW baseline AS
        SELECT zone_id, field_id, year, bin, cdl_code, n_obs, {rels}, {baselines},
               n_prior_years, {residuals}
        FROM (
            SELECT *, {windowed},
                   count(rel_{INDICES[0]}_clean) OVER prior AS n_prior_years
            FROM zone_year_bin
            WINDOW prior AS (
                PARTITION BY zone_id, bin ORDER BY year
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            )
        )
    """)
    _label_baseline_view(con)


def _label_baseline_view(con):
    """Leave-one-year-out baseline for the label. SPEC Section 10.

    Every other year in the record, earlier and later, minus the target year.
    Computed as the partition total less the target year's own contribution,
    so a year can never appear in its own label baseline. Built separately
    from `baseline` so that the feature and the label never share one
    estimated baseline and its error.
    """
    first = INDICES[0]
    loo = ", ".join(
        f"(sum(rel_{n}_clean) OVER z - coalesce(rel_{n}_clean, 0)) / "
        f"nullif(count(rel_{n}_clean) OVER z - (rel_{n}_clean IS NOT NULL)::INT, 0) "
        f"AS label_baseline_{n}"
        for n in INDICES
    )
    residuals = ", ".join(f"rel_{n} - label_baseline_{n} AS label_residual_{n}" for n in INDICES)
    rels = ", ".join(f"rel_{n}" for n in INDICES)
    baselines = ", ".join(f"label_baseline_{n}" for n in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW label_baseline AS
        SELECT zone_id, field_id, year, bin, cdl_code, n_obs, {rels}, {baselines},
               level_{first}, n_label_years, {residuals}
        FROM (
            SELECT *, {loo},
                   count(rel_{first}_clean) OVER z
                     - (rel_{first}_clean IS NOT NULL)::INT AS n_label_years
            FROM zone_year_bin
            WINDOW z AS (PARTITION BY zone_id, bin)
        )
    """)


def supported_view(con, min_prior_years=config.MIN_PRIOR_YEARS):
    """The baseline cells that later steps may use.

    Every consumer reads `supported_baseline`, never `baseline`. The floor is
    applied here rather than inside `baseline` so that the raw prior-year count
    of every cell, including the ones excluded, stays inspectable. Without that,
    the share of cells the floor removes could not be reported.
    """
    floor = int(min_prior_years)
    con.execute(f"""
        CREATE OR REPLACE VIEW supported_baseline AS
        SELECT * FROM baseline WHERE n_prior_years >= {floor}
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW supported_label_baseline AS
        SELECT * FROM label_baseline WHERE n_label_years >= {floor}
    """)


def outcome_views(con, min_prior_years=config.MIN_PRIOR_YEARS,
                  feature_bins=config.FEATURE_BINS, label_bins=config.LABEL_BINS):
    """One label and one feature per zone-year. Step 2 second amendment, Decision 7.

    zone_year_label: mean NDVI residual over supported cells in the label window,
        against the leave-one-year-out baseline, with the number of cells used.
        Also carries `level_ndvi`, the raw index over the same cells with no
        baseline subtracted, which is the secondary label of SPEC Section 10.
        Both labels sit on one view so they cover exactly the same zone-years;
        two populations would make "reported under both labels" a comparison
        of different things.
    zone_year_feature: NDVI residual in the latest supported cell in the feature
        window, against the strictly prior baseline, with the bin it came from.

    A zone-year with no supported cell in a window has no row, which is what the
    Decision 9 gate counts.
    """
    floor = int(min_prior_years)
    label_lo, label_hi = (int(b) for b in label_bins)
    feat_lo, feat_hi = (int(b) for b in feature_bins)
    con.execute(f"""
        CREATE OR REPLACE VIEW zone_year_label AS
        SELECT zone_id, field_id, year, any_value(cdl_code) AS cdl_code,
               avg(label_residual_ndvi) AS label_ndvi,
               avg(level_ndvi) AS level_ndvi, count(*) AS n_label_cells
        FROM label_baseline
        WHERE bin BETWEEN {label_lo} AND {label_hi} AND n_label_years >= {floor}
        GROUP BY zone_id, field_id, year
    """)
    # One row, not three aggregates. S3 compares indices against each other, so
    # they have to describe the same observation; picking each by its own
    # arg_max lets a null in one index silently pull it back to an earlier date
    # while the others stay put, and the "divergence" then measures the
    # calendar. Step 5, Decision 17. This also removes an inconsistency that
    # was already here, where feature_ndvi came from arg_max and feature_bin
    # from a separate max(bin), which name different cells once a null exists.
    features = ", ".join(f"residual_{name} AS feature_{name}" for name in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW zone_year_feature AS
        SELECT zone_id, field_id, year, cdl_code, {features}, bin AS feature_bin
        FROM baseline
        WHERE bin BETWEEN {feat_lo} AND {feat_hi} AND n_prior_years >= {floor}
        QUALIFY row_number() OVER (
            PARTITION BY zone_id, field_id, year ORDER BY bin DESC
        ) = 1
    """)
