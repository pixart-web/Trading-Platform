from collections.abc import Mapping, Sequence
from datetime import timedelta
from enum import StrEnum

from pydantic import Field, ValidationError

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.market import Candle, CandleQuery, UTCDateTime
from pocket_alpha.domain.models import DomainModel


class ReasonCode(StrEnum):
    STALE_DATA = "STALE_DATA"
    MISSING_INTERVAL = "MISSING_INTERVAL"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    INVALID_OHLC = "INVALID_OHLC"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_VOLUME = "INVALID_VOLUME"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    MALFORMED_VALUE = "MALFORMED_VALUE"
    UNEXPECTED_RECORD = "UNEXPECTED_RECORD"


class Severity(StrEnum):
    OK = "OK"
    ERROR = "ERROR"


class FreshnessPolicy(DomainModel):
    # None explicitly permits old historical data, never future data.
    max_age: timedelta | None = Field(default=None, gt=timedelta(0))
    future_tolerance: timedelta = Field(default=timedelta(0), ge=timedelta(0))


class DataQualityResult(DomainModel):
    valid: bool
    severity: Severity
    reason_codes: tuple[ReasonCode, ...]
    warnings: tuple[str, ...] = ()
    timestamp: UTCDateTime
    source: str
    affected_records: tuple[int, ...]
    missing_intervals: tuple[UTCDateTime, ...]


class DataRejected(Exception):
    def __init__(self, quality: DataQualityResult) -> None:
        self.quality = quality
        super().__init__(",".join(quality.reason_codes))


def inspect_candles(
    records: Sequence[Mapping[str, object]],
    query: CandleQuery,
    source: str,
    policy: FreshnessPolicy,
    clock: Clock,
) -> tuple[tuple[Candle, ...], DataQualityResult]:
    now = utc(clock.now())
    reasons: set[ReasonCode] = set()
    affected: set[int] = set()
    candles: list[Candle] = []
    seen: set[UTCDateTime] = set()
    previous: UTCDateTime | None = None
    expected = set(query.schedule())
    for index, record in enumerate(records):
        local: set[ReasonCode] = set()
        try:
            candle = Candle.model_validate(record)
        except ValidationError as error:
            for item in error.errors():
                field = item["loc"][0] if item["loc"] else ""
                message = item["msg"]
                if "INVALID_OHLC" in message:
                    local.add(ReasonCode.INVALID_OHLC)
                elif "INVALID_TIMESTAMP" in message or field in (
                    "open_time",
                    "close_time",
                    "received_at",
                ):
                    local.add(ReasonCode.INVALID_TIMESTAMP)
                elif field in ("open", "high", "low", "close"):
                    local.add(ReasonCode.INVALID_PRICE)
                elif field == "volume":
                    local.add(ReasonCode.INVALID_VOLUME)
                else:
                    local.add(ReasonCode.MALFORMED_VALUE)
            reasons.update(local)
            affected.add(index)
            continue
        if (
            candle.market_id != query.market_id
            or candle.timeframe != query.timeframe
            or candle.source != source
            or candle.open_time not in expected
            or candle.close_time > query.end
        ):
            local.add(ReasonCode.UNEXPECTED_RECORD)
        if candle.open_time in seen:
            local.add(ReasonCode.DUPLICATE_RECORD)
        if previous is not None and candle.open_time < previous:
            local.add(ReasonCode.OUT_OF_ORDER)
        if max(candle.close_time, candle.received_at) > now + policy.future_tolerance:
            local.add(ReasonCode.INVALID_TIMESTAMP)
        if policy.max_age is not None and now - candle.close_time > policy.max_age:
            local.add(ReasonCode.STALE_DATA)
        seen.add(candle.open_time)
        previous = candle.open_time
        candles.append(candle)
        reasons.update(local)
        if local:
            affected.add(index)
    missing = tuple(sorted(expected - seen))
    if missing:
        reasons.add(ReasonCode.MISSING_INTERVAL)
    result = DataQualityResult(
        valid=not reasons,
        severity=Severity.ERROR if reasons else Severity.OK,
        reason_codes=tuple(sorted(reasons)),
        timestamp=now,
        source=source,
        affected_records=tuple(sorted(affected)),
        missing_intervals=missing,
    )
    return tuple(candles), result
