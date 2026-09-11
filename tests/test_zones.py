from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.intelligence.zones.models import ZoneRole, ZoneSpec
from pocket_alpha.intelligence.zones.service import SupportResistance, _calculate
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, START, sample
from tests.test_market_api import client_for, parameters
from tests.test_market_structure import SPEC, bars, query

SPEC_Z = ZoneSpec(structure=SPEC)


def test_bounds_confirmation_and_explained_strength() -> None:
    data = bars((10, 14, 10, 13, 14, 10))
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC_Z)
    assert not result[0].zones and not result[1].zones
    zone = result[2].zones[0]
    assert zone.role == ZoneRole.RESISTANCE
    assert (zone.lower, zone.center, zone.upper) == (Decimal("14.5"), Decimal(15), Decimal("15.5"))
    assert zone.first_seen == START + timedelta(hours=3)
    assert zone.contacts == 0 and zone.pivot_count == 1
    assert zone.confidence is None and zone.confidence_reason == "UNCALIBRATED"
    assert zone.strength == 30 == sum(zone.components.model_dump().values())
    assert result[-1].zones[0].pivot_count == 2
    assert result[-1].zones[0].lower == zone.lower
    assert result[-1].zones[0].upper == zone.upper


def test_contacts_are_episodes_and_flips_start_new_visible_role() -> None:
    data = list(bars((10, 14, 10, 13, 13, 10, 13, 17, 18, 10)))
    for i in (3, 4, 6):
        data[i] = sample(i, open="13", close="13", high="15", low="12")
    result = _calculate(tuple(data), query(len(data)), FreshnessPolicy(), SPEC_Z)
    key = result[2].zones[0].zone_id
    zones = [next(z for z in s.zones if z.zone_id == key) for s in result[2:]]
    assert zones[1].contacts == zones[2].contacts == 1
    assert zones[4].contacts == 2 and zones[4].rejections == 2
    assert zones[5].role == ZoneRole.SUPPORT and zones[5].flips == 1
    assert zones[5].visible_from == START + timedelta(hours=8)
    assert zones[6].flips == 1
    assert zones[7].role == ZoneRole.RESISTANCE and zones[7].flips == 2
    assert zones[7].visible_from == START + timedelta(hours=10)
    assert zones[0].role == ZoneRole.RESISTANCE and zones[0].flips == 0


@pytest.mark.parametrize("maximum,age", [(1, 1), (4, 3), (24, 200)])
def test_prefix_invariance_caps_expiry_and_context(maximum: int, age: int) -> None:
    data = bars()
    spec = ZoneSpec(structure=SPEC, max_zones=maximum, max_age_bars=age)
    full = _calculate(data, query(len(data)), FreshnessPolicy(), spec)
    with localcontext() as context:
        context.prec = 3
        assert _calculate(data, query(len(data)), FreshnessPolicy(), spec) == full
    for length in range(1, len(data) + 1):
        assert _calculate(data[:length], query(length), FreshnessPolicy(), spec) == full[:length]
    assert all(len(s.zones) <= maximum for s in full)
    assert all(z.age_bars <= age and 0 <= z.strength <= 100 for s in full for z in s.zones)
    changed = (*data[:7], *(sample(i, high="1000", close="900") for i in range(7, len(data))))
    assert _calculate(changed, query(len(data)), FreshnessPolicy(), spec)[:7] == full[:7]


def test_expired_zone_disappears_and_old_snapshot_survives() -> None:
    data = bars((10, 14, 10, 10, 10, 10))
    result = _calculate(
        data, query(len(data)), FreshnessPolicy(), ZoneSpec(structure=SPEC, max_age_bars=1)
    )
    assert result[2].zones and result[3].zones
    assert not result[4].zones and not result[5].zones


@pytest.mark.parametrize(
    "params",
    [
        {"max_zones": 0},
        {"max_zones": 33},
        {"max_age_bars": True},
        {"minimum_width_bps": "NaN"},
        {"minimum_width_bps": "0.00001"},
        {"range_fraction": "0"},
        {"version": "2"},
        {"extra": 1},
    ],
)
def test_invalid_spec(params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ZoneSpec.model_validate(params)


def test_service_trusted_data_delays_and_bounds(repository: MarketRepository) -> None:
    service = SupportResistance(MarketReplay(repository, CLOCK))
    with pytest.raises(DataRejected):
        service.analyze(query(3), FreshnessPolicy())
    data = list(bars())
    data[0] = sample(0, **{**data[0].model_dump(), "received_at": START + timedelta(hours=30)})
    repository.put(tuple(data))
    result = service.analyze(query(len(data)), FreshnessPolicy(), SPEC_Z)
    assert all(s.available_at == START + timedelta(hours=30) for s in result)
    assert all(z.first_seen >= START + timedelta(hours=30) for s in result for z in s.zones)
    assert result[-1].model_validate_json(result[-1].model_dump_json()) == result[-1]
    with pytest.raises(ValidationError):
        result[-1].zones[0].strength = 0
    with pytest.raises(DataRejected):
        service.analyze(query(len(data)), FreshnessPolicy(max_age=timedelta(minutes=1)))
    with pytest.raises(ValueError):
        service.analyze(query(2001), FreshnessPolicy())
    closed = CandleQuery.model_validate(
        {
            **query(1).model_dump(),
            "start": START - timedelta(hours=1),
            "end": START,
            "expected_opens": (),
        }
    )
    assert service.analyze(closed, FreshnessPolicy()) == ()


def test_api_atomic_candles_zones_and_quality(repository: MarketRepository) -> None:
    client = client_for(repository)
    url = "/api/v1/markets/test-market/zones"
    assert client.get(url, params=parameters()).status_code == 422
    repository.put(bars())
    params = {**parameters(), "end": (START + timedelta(hours=14)).isoformat()}
    response = client.get(url, params=params)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert len(body["candles"]) == body["snapshot"]["input_count"] == 14
    assert body["quality"]["valid"] and not body["truncated"]
    assert body["snapshot"]["zones"]
    assert body["snapshot"]["zones"][0]["confidence"] is None
    assert client.post(url, json={}).status_code == 405
    assert client.get("/api/v1/markets/missing/zones", params=params).status_code == 404
    for changes in (
        {"start": "2025-01-01T00:00:00"},
        {"timeframe": "bad"},
        {"end": (START + timedelta(hours=1001)).isoformat()},
    ):
        assert client.get(url, params={**params, **changes}).status_code == 422


def test_zone_model_rejects_inconsistent_bounds_and_strength() -> None:
    valid = _calculate(bars(), query(14), FreshnessPolicy(), SPEC_Z)[2].zones[0]
    for change in (
        {"lower": valid.upper},
        {"strength": 100},
        {"confidence": "0.9"},
        {"visible_from": START},
        {"upper": "Infinity"},
    ):
        with pytest.raises(ValidationError):
            type(valid).model_validate({**valid.model_dump(), **change})


def test_internal_size_limit_and_bounded_evidence() -> None:
    data = bars(tuple(100 + i % 5 for i in range(2001)))
    with pytest.raises(ValueError):
        _calculate(data, query(2001), FreshnessPolicy(), SPEC_Z)
    result = _calculate(data[:200], query(200), FreshnessPolicy(), SPEC_Z)
    assert all(len(z.evidence) <= 32 for s in result for z in s.zones)
    assert any(z.pivot_count > 32 for z in result[-1].zones)


def test_api_storage_failure_is_sanitized() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.exc import SQLAlchemyError

    from pocket_alpha.main import create_app

    broken = create_engine("sqlite://")

    def fail(*args: object) -> None:
        raise SQLAlchemyError("private credentials")

    event.listen(broken, "connect", fail)
    app = create_app()
    app.state.engine = broken
    response = TestClient(app).get("/api/v1/markets/test-market/zones", params=parameters())
    assert response.status_code == 503
    assert "private credentials" not in response.text
    broken.dispose()
