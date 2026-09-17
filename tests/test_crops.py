"""Tests for the crop registry.

SPEC Section 8 and DESIGN D4: crop knowledge is a table keyed by CDL code, and
no crop name may appear in a conditional anywhere in the codebase. The registry
is the single place a crop name is allowed to be written down.
"""

import pytest

from orbitalscout import crops


def test_registry_is_keyed_by_cdl_code():
    assert crops.get(1).name == "corn"
    assert crops.get(5).name == "soybean"


def test_unknown_cdl_code_raises_rather_than_defaulting():
    """A silent default would apply corn's thresholds to an unlisted crop."""
    with pytest.raises(KeyError, match="176"):
        crops.get(176)  # grassland/pasture, deliberately not in the registry


def test_every_registry_row_carries_what_gdd_needs():
    for code in crops.codes():
        row = crops.get(code)
        assert row.gdd_base_f < row.gdd_cap_f
        assert row.nass_commodity, "the planting-date anchor needs a NASS commodity"


def test_corn_uses_the_standard_base_and_cap():
    corn = crops.get(1)
    assert corn.gdd_base_f == 50.0
    assert corn.gdd_cap_f == 86.0


def test_registry_codes_match_the_configured_crops():
    from orbitalscout import config
    assert set(crops.codes()) == set(config.CROP_CDL_CODES)
