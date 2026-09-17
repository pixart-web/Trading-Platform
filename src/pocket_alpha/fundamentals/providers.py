import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from email.message import Message
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import Field

from pocket_alpha.domain.market import UTCDateTime
from pocket_alpha.domain.models import Currency, DomainModel
from pocket_alpha.fundamentals.models import FundamentalMetric, Value


class FundamentalProviderError(Exception):
    """A real provider failed; callers must not substitute synthetic facts."""


class ProviderFact(DomainModel):
    metric: FundamentalMetric
    value: Value
    currency: Currency | None = None
    unit: str = Field(min_length=1, max_length=64)
    period_start: date | None = None
    period_end: date
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str
    source_concept: str = Field(min_length=1, max_length=128)
    source_record_id: str
    accession_number: str | None = None
    published_at: UTCDateTime


@dataclass(frozen=True)
class FundamentalPage:
    records: tuple[ProviderFact, ...]
    next_cursor: str | None = None


class FundamentalProvider(Protocol):
    @property
    def source(self) -> str: ...

    def facts(self, instrument_id: str, cursor: str | None = None) -> FundamentalPage: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


MAX_RESPONSE_BYTES = 20_000_000


class UrllibTransport:
    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                response_headers: Message = response.headers
                return HttpResponse(
                    status=response.status,
                    body=response.read(MAX_RESPONSE_BYTES + 1),
                    headers={key.lower(): value for key, value in response_headers.items()},
                )
        except HTTPError as error:
            return HttpResponse(
                status=error.code,
                body=error.read(MAX_RESPONSE_BYTES + 1),
                headers={key.lower(): value for key, value in error.headers.items()},
            )
        except (URLError, TimeoutError, OSError) as error:
            raise FundamentalProviderError("SEC transport failed") from error


SEC_TAGS: dict[str, FundamentalMetric] = {
    "GrossProfit": FundamentalMetric.GROSS_PROFIT,
    "OperatingIncomeLoss": FundamentalMetric.OPERATING_INCOME,
    "NetIncomeLoss": FundamentalMetric.NET_INCOME,
    "NetCashProvidedByUsedInOperatingActivities": FundamentalMetric.OPERATING_CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": FundamentalMetric.CAPITAL_EXPENDITURE,
    "StockholdersEquity": FundamentalMetric.EQUITY,
    "Revenues": FundamentalMetric.REVENUE,
    "RevenueFromContractWithCustomerExcludingAssessedTax": FundamentalMetric.REVENUE,
    "EarningsPerShareDiluted": FundamentalMetric.EPS_DILUTED,
    "CashAndCashEquivalentsAtCarryingValue": FundamentalMetric.CASH,
    "LongTermDebtAndFinanceLeaseObligations": FundamentalMetric.LONG_TERM_DEBT,
    "LongTermDebt": FundamentalMetric.LONG_TERM_DEBT,
}


class SecCompanyFactsProvider:
    source = "sec-companyfacts"

    def __init__(
        self,
        user_agent: str,
        *,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 10,
        maximum_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError("SEC User-Agent must identify an operator contact")
        if not 1 <= maximum_attempts <= 5 or not 1 <= timeout_seconds <= 30:
            raise ValueError("SEC retry and timeout bounds are invalid")
        self.user_agent = user_agent.strip()
        self.transport = transport or UrllibTransport()
        self.timeout_seconds = timeout_seconds
        self.maximum_attempts = maximum_attempts
        self.sleep = sleep
        self.monotonic = monotonic
        self.last_request: float | None = None

    def facts(self, instrument_id: str, cursor: str | None = None) -> FundamentalPage:
        if cursor is not None:
            raise FundamentalProviderError("SEC company facts is a single bounded document")
        cik = instrument_id.strip()
        if not cik.isdigit() or not 1 <= len(cik) <= 10:
            raise ValueError("SEC instrument identity must be a numeric CIK")
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        response = self._get(url)
        try:
            payload = json.loads(response.body, parse_float=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FundamentalProviderError("SEC returned invalid JSON") from error
        if not isinstance(payload, dict) or str(payload.get("cik", "")).lstrip("0") != cik.lstrip(
            "0"
        ):
            raise FundamentalProviderError("SEC payload identity does not match requested CIK")
        return FundamentalPage(records=self._parse(payload))

    def _get(self, url: str) -> HttpResponse:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        for attempt in range(self.maximum_attempts):
            if self.last_request is not None:
                self.sleep(max(0.0, 0.2 - (self.monotonic() - self.last_request)))
            self.last_request = self.monotonic()
            try:
                response = self.transport.get(url, headers, self.timeout_seconds)
            except FundamentalProviderError:
                if attempt + 1 == self.maximum_attempts:
                    raise
                self.sleep(min(0.5 * 2**attempt, 5.0))
                continue
            if len(response.body) > MAX_RESPONSE_BYTES:
                raise FundamentalProviderError("SEC response exceeds the bounded byte limit")
            if response.status == 200:
                return response
            if response.status not in (429, 500, 502, 503, 504):
                raise FundamentalProviderError(
                    f"SEC request rejected with status {response.status}"
                )
            if attempt + 1 < self.maximum_attempts:
                retry_after = response.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * 2**attempt
                except ValueError:
                    delay = 0.5 * 2**attempt
                # Never shorten an explicit provider embargo and retry early.
                if not 0 <= delay <= 5:
                    raise FundamentalProviderError("SEC retry embargo exceeds bounded wait")
                self.sleep(delay)
        raise FundamentalProviderError("SEC request failed after bounded retries")

    def _parse(self, payload: object) -> tuple[ProviderFact, ...]:
        if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
            raise FundamentalProviderError("SEC company facts payload has no facts object")
        us_gaap = payload["facts"].get("us-gaap", {})
        if not isinstance(us_gaap, dict):
            return ()
        result: list[ProviderFact] = []
        for tag, metric in SEC_TAGS.items():
            concept = us_gaap.get(tag)
            if not isinstance(concept, dict) or not isinstance(concept.get("units"), dict):
                continue
            for unit, records in concept["units"].items():
                if not isinstance(unit, str) or not isinstance(records, list):
                    continue
                for raw in records:
                    fact = self._fact(tag, metric, unit, raw)
                    if fact is not None:
                        result.append(fact)
        result.sort(key=lambda fact: (fact.metric.value, fact.period_end, fact.source_record_id))
        if len(result) > 10000:
            raise FundamentalProviderError("SEC company facts exceeds the bounded record limit")
        return tuple(result)

    def _fact(
        self, tag: str, metric: FundamentalMetric, unit: str, raw: object
    ) -> ProviderFact | None:
        if not isinstance(raw, dict):
            raise FundamentalProviderError("SEC contains a malformed fact")
        required = ("val", "end", "filed", "form", "accn")
        if any(raw.get(key) is None for key in required):
            raise FundamentalProviderError("SEC fact is missing required provenance")
        try:
            value = Decimal(str(raw["val"]))
            period_end = date.fromisoformat(str(raw["end"]))
            period_start = date.fromisoformat(str(raw["start"])) if raw.get("start") else None
            filed = date.fromisoformat(str(raw["filed"]))
        except (InvalidOperation, ValueError) as error:
            raise FundamentalProviderError("SEC contains invalid financial values") from error
        numerator = unit.split("/")[0]
        currency = numerator if numerator in {"USD", "EUR", "GBP", "JPY", "CAD"} else None
        source_id = "|".join(
            (
                str(raw["accn"]),
                "us-gaap",
                tag,
                unit,
                str(raw.get("start", "")),
                str(raw["end"]),
                str(raw.get("frame", "")),
            )
        )
        return ProviderFact(
            metric=metric,
            value=value,
            currency=currency,
            unit=unit,
            period_start=period_start,
            period_end=period_end,
            fiscal_year=int(raw["fy"]) if raw.get("fy") is not None else None,
            fiscal_period=str(raw["fp"]) if raw.get("fp") is not None else None,
            form=str(raw["form"]),
            source_concept=f"us-gaap:{tag}",
            source_record_id=source_id,
            accession_number=str(raw["accn"]),
            published_at=datetime.combine(filed, datetime.min.time(), tzinfo=UTC),
        )
