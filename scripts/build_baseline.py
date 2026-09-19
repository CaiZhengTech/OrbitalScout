"""Build the Step 2 baseline on real data, then report its support.

Two phases, so memory stays bounded over 150 million rows:

1. Field medians, once, over every zone. The median has to see the whole field.
2. The windowed baseline, over ten deterministic chunks of zones (hash of the
   zone id), each reusing the phase 1 medians.

Output lands in data/baseline/, one Parquet per chunk, plus the field stats.
Then the prior-year support of the held-out years is reported, because that is
the gate: if the floor of MIN_PRIOR_YEARS excludes more than a fifth of cells
anywhere, Step 2 stops for a decision.

Run:
    python scripts/build_baseline.py              # baseline chunks, then the cell gate
    python scripts/build_baseline.py --outcomes   # label and feature per zone-year, then the
                                                  # Decision 9 gate (reuses the field medians)
"""

import os
import pathlib
import sys
import time

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import baseline, config, crops  # noqa: E402
from orbitalscout.ingest import weather  # noqa: E402

OUT = pathlib.Path("data/baseline")
CHUNKS = 10
HELD_OUT = (2023, 2024, 2025)
GATE_MAX_EXCLUDED = 0.20


def chunks(name):
    """The ten chunk files for one output, and nothing else.

    Never write `name_*.parquet` by hand. Diagnostics write their own outputs
    into this directory, so `label_*.parquet` also matches
    `label_noevent_*.parquet` and reads every zone-year twice, once with event
    observations excluded, with no error and a plausible row count. Found at
    Step 4, after it had been latent since Step 2.
    """
    return f"{OUT.as_posix()}/{name}_[0-9][0-9].parquet"


def connect():
    con = duckdb.connect()
    tmp = pathlib.Path("data/duckdb_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute("SET memory_limit = '2GB'")
    con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
    con.execute("ATTACH 'data/orbitalscout.duckdb' AS src (READ_ONLY)")
    con.execute("CREATE VIEW fields AS SELECT * FROM src.fields")
    con.execute("CREATE VIEW zones AS SELECT * FROM src.zones")
    daily = pd.read_csv("orbitalscout/frozen/weather_daily.csv", dtype={"date": str})
    planting = pd.read_csv("orbitalscout/frozen/planting_dates.csv")
    con.register("gdd", weather.gdd_table(daily, planting))
    return con


def zone_obs_view(con, chunk=None):
    where = "" if chunk is None else f" WHERE hash(zone_id) % {CHUNKS} = {chunk}"
    con.execute(
        "CREATE OR REPLACE VIEW zone_obs AS "
        f"SELECT * FROM read_parquet('data/zone_obs_*.parquet'){where}"
    )


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    stats_path = (OUT / "field_date_stats.parquet").as_posix()

    started = time.time()
    print("phase 1: field medians over all zones ...", flush=True)
    zone_obs_view(con)
    baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC)
    con.execute(f"COPY field_date_stats TO '{stats_path}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{stats_path}')").fetchone()[0]
    print(f"  {n:,} field-dates in {time.time() - started:.0f}s", flush=True)

    for chunk in range(CHUNKS):
        t = time.time()
        zone_obs_view(con, chunk)
        baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC,
                             field_stats=stats_path)
        target = (OUT / f"baseline_{chunk:02d}.parquet").as_posix()
        con.execute(f"COPY baseline TO '{target}' (FORMAT PARQUET)")
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{target}')").fetchone()[0]
        print(f"phase 2: chunk {chunk + 1}/{CHUNKS}, {rows:,} zone-year-bins, "
              f"{time.time() - t:.0f}s", flush=True)
    con.close()


def report_support():
    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    con.execute(f"CREATE VIEW b AS SELECT * FROM read_parquet('{chunks('baseline')}')")
    total = con.execute("SELECT count(*) FROM b").fetchone()[0]
    print(f"\nbaseline cells, all years: {total:,}")

    floor = config.MIN_PRIOR_YEARS
    held = ", ".join(str(y) for y in HELD_OUT)
    print(f"\nprior-year support in held-out years; floor = {floor}\n")

    print("by year:")
    print(f"  {'year':>5} {'cells':>11} {'0':>6} {'1':>6} {'2':>6} {'3':>6} {'4':>6} {'5+':>6} {'excluded':>9}")
    worst = []
    for row in con.execute(f"""
        SELECT year, count(*),
               avg((n_prior_years = 0)::INT), avg((n_prior_years = 1)::INT),
               avg((n_prior_years = 2)::INT), avg((n_prior_years = 3)::INT),
               avg((n_prior_years = 4)::INT), avg((n_prior_years >= 5)::INT),
               avg((n_prior_years < {floor})::INT)
        FROM b WHERE year IN ({held}) GROUP BY year ORDER BY year
    """).fetchall():
        year, cells, *shares = row
        print(f"  {year:>5} {cells:>11,} " + " ".join(f"{100*v:>5.1f}%" for v in shares[:-1])
              + f" {100*shares[-1]:>8.1f}%")
        worst.append((f"{year} overall", shares[-1], cells))

    print("\nexcluded share by year and bin:")
    rows = con.execute(f"""
        SELECT year, bin, count(*), avg((n_prior_years < {floor})::INT)
        FROM b WHERE year IN ({held}) GROUP BY year, bin ORDER BY bin, year
    """).fetchall()
    by_bin = {}
    for year, b, cells, share in rows:
        by_bin.setdefault(b, {})[year] = (share, cells)
        worst.append((f"{year} bin {b}", share, cells))
    print(f"  {'bin':>4} {'GDD':>11} " + " ".join(f"{y:>16}" for y in HELD_OUT))
    for b in sorted(by_bin):
        cells = " ".join(
            f"{100*by_bin[b][y][0]:>6.1f}% ({by_bin[b][y][1]:>7,})" if y in by_bin[b] else f"{'-':>16}"
            for y in HELD_OUT
        )
        lo = b * config.BIN_WIDTH_GDD
        print(f"  {b:>4} {lo:>5}-{lo + config.BIN_WIDTH_GDD:<5} {cells}")

    over = [(label, share, cells) for label, share, cells in worst if share > GATE_MAX_EXCLUDED]
    print(f"\ngate: floor may exclude at most {GATE_MAX_EXCLUDED:.0%} of cells anywhere")
    if over:
        print(f"GATE TRIPPED in {len(over)} place(s):")
        for label, share, cells in sorted(over, key=lambda r: -r[1]):
            print(f"  {label:<16} {100*share:5.1f}% excluded of {cells:,} cells")
        return 1
    print("gate passed")
    return 0


def build_outcomes():
    """One label and one feature per zone-year, per chunk, reusing field medians."""
    stats_path = (OUT / "field_date_stats.parquet").as_posix()
    if not pathlib.Path(stats_path).exists():
        raise SystemExit("field medians missing; run the default build first")
    con = connect()
    for chunk in range(CHUNKS):
        t = time.time()
        zone_obs_view(con, chunk)
        baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC,
                             field_stats=stats_path)
        baseline.outcome_views(con)
        for view, name in (("zone_year_label", "label"), ("zone_year_feature", "feature")):
            con.execute(f"COPY {view} TO '{(OUT / f'{name}_{chunk:02d}.parquet').as_posix()}' "
                        "(FORMAT PARQUET)")
        print(f"outcomes: chunk {chunk + 1}/{CHUNKS}, {time.time() - t:.0f}s", flush=True)
    con.close()


def report_outcome_gate():
    """Decision 9: share of eligible zone-years with no label, and with no feature.

    Eligible means a zone-year whose field grew a registry crop that year; any
    other zone-year cannot carry a label by construction and is counted apart.
    """
    con = connect()
    codes = ", ".join(str(c) for c in crops.codes())
    held = ", ".join(str(y) for y in HELD_OUT)
    crop_cols = ", ".join(f"crop_{y}" for y in config.YEARS)
    con.execute(f"""
        CREATE TEMP TABLE field_crop AS
        SELECT field_id, CAST(replace(k, 'crop_', '') AS INTEGER) AS year, cdl_code
        FROM (UNPIVOT fields ON {crop_cols} INTO NAME k VALUE cdl_code)
    """)
    con.execute(f"CREATE VIEW lab AS SELECT * FROM read_parquet('{chunks('label')}')")
    con.execute(f"CREATE VIEW fea AS SELECT * FROM read_parquet('{chunks('feature')}')")

    print(f"\nDecision 9 gate: at most {GATE_MAX_EXCLUDED:.0%} of eligible zone-years may lack a label,")
    print("and at most the same may lack a feature, in each held-out year.\n")
    rows = con.execute(f"""
        WITH zy AS (
            SELECT z.zone_id, fc.year, fc.cdl_code
            FROM zones z JOIN field_crop fc USING (field_id)
            WHERE fc.year IN ({held})
        )
        SELECT zy.year,
               count(*) FILTER (WHERE zy.cdl_code NOT IN ({codes})) AS ineligible,
               count(*) FILTER (WHERE zy.cdl_code IN ({codes})) AS eligible,
               count(l.zone_id) FILTER (WHERE zy.cdl_code IN ({codes})) AS with_label,
               count(f.zone_id) FILTER (WHERE zy.cdl_code IN ({codes})) AS with_feature
        FROM zy
        LEFT JOIN lab l ON l.zone_id = zy.zone_id AND l.year = zy.year
        LEFT JOIN fea f ON f.zone_id = zy.zone_id AND f.year = zy.year
        GROUP BY zy.year ORDER BY zy.year
    """).fetchall()

    print(f"  {'year':>5} {'eligible':>10} {'no label':>9} {'no feature':>11} {'ineligible (other crop)':>24}")
    tripped = []
    for year, ineligible, eligible, with_label, with_feature in rows:
        no_label = 1 - with_label / eligible
        no_feature = 1 - with_feature / eligible
        print(f"  {year:>5} {eligible:>10,} {100*no_label:>8.1f}% {100*no_feature:>10.1f}% {ineligible:>24,}")
        if no_label > GATE_MAX_EXCLUDED:
            tripped.append(f"{year} no label {100*no_label:.1f}%")
        if no_feature > GATE_MAX_EXCLUDED:
            tripped.append(f"{year} no feature {100*no_feature:.1f}%")

    print("\nlabel cells used per labelled zone-year (bins 8 to 11):")
    for year, *shares in con.execute(f"""
        SELECT year, avg((n_label_cells = 1)::INT), avg((n_label_cells = 2)::INT),
               avg((n_label_cells = 3)::INT), avg((n_label_cells = 4)::INT)
        FROM lab WHERE year IN ({held}) GROUP BY year ORDER BY year
    """).fetchall():
        print(f"  {year}: " + "  ".join(f"{k} cell{'s' if k > 1 else ''} {100*v:5.1f}%"
                                         for k, v in zip(range(1, 5), shares)))

    print("\nbin the feature came from (latest supported vegetative cell):")
    bin_shares = ", ".join(
        f"avg((feature_bin = {b})::INT)" for b in range(config.FEATURE_BINS[1] + 1)
    )
    for year, *shares in con.execute(f"""
        SELECT year, {bin_shares}
        FROM fea WHERE year IN ({held}) GROUP BY year ORDER BY year
    """).fetchall():
        print(f"  {year}: " + "  ".join(f"bin {b} {100*v:4.1f}%" for b, v in enumerate(shares)))

    if tripped:
        print("\nGATE TRIPPED: " + "; ".join(tripped))
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    if "--outcomes" in sys.argv:
        if "--report-only" not in sys.argv:
            build_outcomes()
        raise SystemExit(report_outcome_gate())
    if "--report-only" not in sys.argv:
        build()
    raise SystemExit(report_support())
