"""The GDD origin: the date the state reached 50% planted, per crop per year.

USDA NASS Crop Progress reports cumulative percent planted weekly. The 50%
crossing rarely lands on a reporting date, so it is interpolated linearly
between the week below and the week at or above.

An external published anchor rather than a threshold invented here, and it
anchors the year-level offset that the within-field baseline cannot cancel.
See `docs/reviews/2026-09-17-step2-decisions.md` Decision 1.
"""

import datetime as dt
import os

import requests

from .. import config

QUICKSTATS = "https://quickstats.nass.usda.gov/api/api_GET/"
TARGET_PCT = 50.0


def fifty_percent_date(series):
    """The date the series crosses TARGET_PCT, interpolated between weeks.

    `series` is an iterable of {"week_ending": "YYYY-MM-DD", "pct_planted": n}.
    Raises rather than guessing: a series that never reaches 50% would
    otherwise silently yield a date near harvest, and every phenology bin for
    that crop-year would be shifted by months.
    """
    rows = sorted(
        ({"date": r["week_ending"], "pct": float(r["pct_planted"])} for r in series),
        key=lambda r: r["date"],
    )
    if not rows:
        raise ValueError("planting progress series is empty")
    if rows[-1]["pct"] < TARGET_PCT:
        raise ValueError(
            f"planting progress never reaches {TARGET_PCT:.0f}%, "
            f"peaks at {rows[-1]['pct']:.0f}%"
        )

    previous = None
    for row in rows:
        if row["pct"] >= TARGET_PCT:
            # Already past at the first reading: reporting started late, so use
            # that date rather than extrapolating backwards into no data.
            if previous is None or previous["pct"] >= TARGET_PCT:
                return row["date"]
            span_pct = row["pct"] - previous["pct"]
            if span_pct <= 0:
                return row["date"]
            fraction = (TARGET_PCT - previous["pct"]) / span_pct
            start = dt.date.fromisoformat(previous["date"])
            days = (dt.date.fromisoformat(row["date"]) - start).days
            # Floor, not round. An exact half-day tie (40% to 60% across a
            # 7 day gap lands at 3.5 days) would otherwise fall to Python's
            # banker's rounding, which is deterministic but arbitrary here.
            # Flooring resolves the tie toward the earlier date consistently.
            # The difference is under a day, roughly 10 GDD in a 3,000 GDD
            # season, so what matters is that it is fixed and stated.
            return (start + dt.timedelta(days=int(fraction * days))).isoformat()
        previous = row
    raise ValueError(f"planting progress never reaches {TARGET_PCT:.0f}%")


def fetch_progress(commodity, year, state="IA", api_key=None):
    """Weekly cumulative percent planted from NASS Quick Stats.

    Needs a free key from quickstats.nass.usda.gov/api, read from the
    NASS_API_KEY environment variable if not passed.
    """
    key = api_key or os.environ.get("NASS_API_KEY")
    if not key:
        raise RuntimeError(
            "no NASS API key. Get a free one at quickstats.nass.usda.gov/api "
            "and set NASS_API_KEY."
        )
    response = requests.get(QUICKSTATS, params={
        "key": key,
        "source_desc": "SURVEY",
        "sector_desc": "CROPS",
        "commodity_desc": commodity,
        "statisticcat_desc": "PROGRESS",
        "unit_desc": "PCT PLANTED",
        "state_alpha": state,
        "year": str(year),
        "format": "JSON",
    }, timeout=60)
    response.raise_for_status()
    return [
        {"week_ending": row["week_ending"], "pct_planted": row["Value"]}
        for row in response.json()["data"]
    ]
