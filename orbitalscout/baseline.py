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
    relatives = ", ".join(f"b.{name} - s.med_{name} AS rel_{name}" for name in INDICES)
    con.execute(f"""
        CREATE OR REPLACE VIEW relative_obs AS
        SELECT b.zone_id, b.field_id, b.year, b.date, b.bin, b.cdl_code, {relatives},
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
               {aggregates}, count(*) AS n_obs
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


def supported_view(con, min_prior_years=config.MIN_PRIOR_YEARS):
    """The baseline cells that later steps may use.

    Every consumer reads `supported_baseline`, never `baseline`. The floor is
    applied here rather than inside `baseline` so that the raw prior-year count
    of every cell, including the ones excluded, stays inspectable. Without that,
    the share of cells the floor removes could not be reported.
    """
    con.execute(f"""
        CREATE OR REPLACE VIEW supported_baseline AS
        SELECT * FROM baseline WHERE n_prior_years >= {int(min_prior_years)}
    """)
