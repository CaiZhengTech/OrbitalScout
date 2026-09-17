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
    python scripts/build_baseline.py
"""

import os
import pathlib
import sys
import time

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import baseline, config  # noqa: E402
from orbitalscout.ingest import weather  # noqa: E402

OUT = pathlib.Path("data/baseline")
CHUNKS = 10
HELD_OUT = (2023, 2024, 2025)
GATE_MAX_EXCLUDED = 0.20


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
    con.execute("CREATE VIEW b AS SELECT * FROM read_parquet('data/baseline/baseline_*.parquet')")
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


if __name__ == "__main__":
    if "--report-only" not in sys.argv:
        build()
    raise SystemExit(report_support())
