from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class FrozenClock:
    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", utc(self.instant))

    def now(self) -> datetime:
        return self.instant
