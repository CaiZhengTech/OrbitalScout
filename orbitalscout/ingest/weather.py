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
