"""Daily temperature and growing degree day accumulation.

One series at the AOI centroid, not per field. The temperature field varies by
a fraction of a degree across a 30 km AOI, and any field-to-field difference is
a field-year constant that the within-field baseline of D17 cancels. See
`docs/reviews/2026-09-17-step2-decisions.md` Decision 3.
"""

import pandas as pd
import requests

from .. import config


def fetch_daily(latitude, longitude, start, end):
    """Daily max and min 2m temperature in Fahrenheit from the Open-Meteo archive."""
    response = requests.get(config.WEATHER_ARCHIVE_URL, params={
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start,
        "end_date": end,
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Chicago",
    }, timeout=60)
    response.raise_for_status()
    daily = response.json()["daily"]
    return pd.DataFrame({
        "date": daily["time"],
        "tmax_f": daily["temperature_2m_max"],
        "tmin_f": daily["temperature_2m_min"],
    })


def accumulate(daily, base_f, cap_f, origin=None):
    """Per-day GDD and its cumulative sum from `origin`.

    The standard method: cap the maximum, floor the minimum at the base, take
    the mean, subtract the base, and never go negative. A cold night must not
    subtract heat already accumulated, and a hot day must not count beyond the
    temperature above which the crop stops responding.

    `origin` is the planting anchor. Days before it contribute nothing, because
    accumulation starts at planting and April warmth is not growth.
    """
    out = daily.copy()
    capped = out["tmax_f"].clip(upper=cap_f)
    floored = out["tmin_f"].clip(lower=base_f)
    out["gdd"] = ((capped + floored) / 2.0 - base_f).clip(lower=0.0)

    if origin is not None:
        out.loc[out["date"] < str(origin), "gdd"] = 0.0
    out["gdd_cumulative"] = out["gdd"].cumsum()
    return out


def gdd_table(daily, planting_dates):
    """Cumulative GDD per crop per date, from each crop-year's planting origin.

    Returns columns cdl_code, date, gdd. One row per registry crop per day on or
    after that crop-year's origin. Days before the origin are left out rather
    than given a GDD of zero: before planting the satellite sees bare soil, so
    those observations have no growth stage and must not land in the first bin.

    Thresholds come from the crop registry by CDL code, so no crop name is ever
    branched on here.
    """
    from .. import crops

    daily = daily.copy()
    daily["year"] = daily["date"].str.slice(0, 4).astype(int)
    frames = []
    for row in planting_dates.itertuples(index=False):
        crop = crops.get(row.cdl_code)
        season = daily[daily["year"] == int(row.year)]
        season = season[season["date"] >= str(row.fifty_pct_planted)]
        if season.empty:
            continue
        acc = accumulate(season, crop.gdd_base_f, crop.gdd_cap_f)
        frames.append(pd.DataFrame({
            "cdl_code": int(row.cdl_code),
            "date": acc["date"].values,
            "gdd": acc["gdd_cumulative"].values,
        }))
    return pd.concat(frames, ignore_index=True)
