from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from aeroeyes_monitoring_api.domain.metar import (
    FlightCategory,
    MetarObservation,
    MetarReportType,
)


def _observation(**overrides: object) -> MetarObservation:
    values: dict[str, object] = {
        "station_icao": "SBGR",
        "report_type": MetarReportType.METAR,
        "observed_at": datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc),
        "raw_text": "METAR SBGR 070200Z 16008KT 9999",
    }
    values.update(overrides)
    return MetarObservation(**values)  # type: ignore[arg-type]


def test_metar_observation_is_immutable_and_canonicalizes_icao() -> None:
    observation = _observation(station_icao=" sbgr ")

    assert observation.station_icao == "SBGR"
    with pytest.raises(FrozenInstanceError):
        observation.raw_text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("station", ["SBG", "SBG1", "SÁGR"])
def test_metar_observation_rejects_invalid_icao(station: str) -> None:
    with pytest.raises(ValueError, match="ASCII alphabetic"):
        _observation(station_icao=station)


def test_metar_observation_requires_aware_timestamp_and_raw_text() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _observation(observed_at=datetime(2026, 9, 7, 2, 0))
    with pytest.raises(ValueError, match="non-empty"):
        _observation(raw_text="  ")


def test_metar_observation_accepts_all_enum_values() -> None:
    assert set(MetarReportType) == {MetarReportType.METAR, MetarReportType.SPECI}
    assert set(FlightCategory) == {
        FlightCategory.VFR,
        FlightCategory.MVFR,
        FlightCategory.IFR,
        FlightCategory.LIFR,
    }


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("wind_direction_deg", 361, "0 to 360"),
        ("wind_speed_kt", float("inf"), "finite"),
        ("visibility_sm", -1.0, "negative"),
        ("ceiling_ft_agl", -1, "non-negative"),
        ("altimeter_hpa", 0.0, "positive"),
    ],
)
def test_metar_observation_rejects_invalid_numeric_invariants(
    field_name: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _observation(**{field_name: value})


def test_metar_observation_keeps_calm_and_variable_wind_distinct() -> None:
    calm = _observation(wind_direction_deg=0, wind_speed_kt=0.0)
    variable = _observation(wind_direction_deg=None, wind_variable=True)

    assert (calm.wind_direction_deg, calm.wind_variable) == (0, False)
    assert (variable.wind_direction_deg, variable.wind_variable) == (None, True)


def test_variable_wind_cannot_have_numeric_direction() -> None:
    with pytest.raises(ValueError, match="variable wind"):
        _observation(wind_direction_deg=180, wind_variable=True)
