"""The crop registry. The only place a crop name is written down.

SPEC Section 8 and DESIGN D4: crop knowledge is a table keyed by CDL code, and
no crop name may appear in a conditional anywhere else. Adding a crop means
adding a row here, not editing logic.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Crop:
    cdl_code: int
    name: str
    gdd_base_f: float
    gdd_cap_f: float
    nass_commodity: str  # USDA NASS Quick Stats commodity_desc, for the 50% planted date
    note: str = ""


_REGISTRY = {
    1: Crop(
        cdl_code=1, name="corn", gdd_base_f=50.0, gdd_cap_f=86.0,
        nass_commodity="CORN",
    ),
    5: Crop(
        cdl_code=5, name="soybean", gdd_base_f=50.0, gdd_cap_f=86.0,
        nass_commodity="SOYBEANS",
        note=(
            "Soybean development is photoperiod and maturity-group driven and "
            "there is no authoritative GDD-per-stage table, so its phenology "
            "alignment is weaker than corn's. The cap is carried over from corn "
            "for want of a better published figure, which is a known weakness "
            "reported in RESULTS.md rather than hidden."
        ),
    ),
}


def get(cdl_code):
    """The registry row for a CDL code.

    Raises rather than defaulting. A default would quietly apply one crop's
    thresholds to another, which is the kind of wrongness that produces
    plausible numbers.
    """
    try:
        return _REGISTRY[int(cdl_code)]
    except KeyError:
        raise KeyError(
            f"CDL code {cdl_code} is not in the crop registry. Add a row to "
            "orbitalscout/crops.py rather than branching on it."
        ) from None


def codes():
    """Every CDL code the registry knows."""
    return tuple(sorted(_REGISTRY))
