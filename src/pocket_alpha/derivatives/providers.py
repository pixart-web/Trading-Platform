from dataclasses import dataclass
from typing import Protocol

from pocket_alpha.derivatives.models import DerivativeSample


class DerivativeProviderError(Exception):
    """Provider failure cannot be replaced with synthetic derivative data."""


@dataclass(frozen=True)
class DerivativePage:
    records: tuple[DerivativeSample, ...]
    next_cursor: str | None = None


class DerivativeProvider(Protocol):
    @property
    def source(self) -> str: ...

    def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage: ...
