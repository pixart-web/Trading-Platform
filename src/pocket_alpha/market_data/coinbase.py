import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from pocket_alpha.common.clock import utc
from pocket_alpha.common.public_http import PublicClient, PublicDataError
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.market_data.providers import CandlePage, ProviderError, ProviderMapping

SUPPORTED = {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.D1}


class CoinbaseHistoricalProvider:
    """Public spot candles only; no credentials, orders, synthetic fallback or streaming."""

    source = "coinbase-exchange"

    def __init__(self, client: PublicClient | None = None) -> None:
        self.client = client or PublicClient()

    def candles(
        self,
        query: CandleQuery,
        mapping: ProviderMapping,
        cursor: str | None = None,
    ) -> CandlePage:
        if mapping.source != self.source or mapping.market_id != query.market_id:
            raise ValueError("Coinbase requires explicit matching provider mapping")
        if not re.fullmatch(r"[A-Z0-9]{2,12}-[A-Z0-9]{2,12}", mapping.instrument_id):
            raise ValueError("Coinbase product identity invalid")
        if query.timeframe not in SUPPORTED or query.expected_opens is not None:
            raise ValueError("Coinbase supports native fixed continuous candle schedules only")
        granularity = int(query.timeframe.duration.total_seconds())
        if (
            query.start.microsecond
            or query.end.microsecond
            or (
                int(query.start.timestamp()) % granularity
                or int(query.end.timestamp()) % granularity
            )
        ):
            raise ValueError("Coinbase candle boundaries must align with native UTC buckets")
        try:
            start = utc(datetime.fromisoformat(cursor)) if cursor else query.start
        except ValueError as error:
            raise ProviderError("Coinbase cursor invalid") from error
        if not query.start <= start < query.end or (start - query.start) % query.timeframe.duration:
            raise ProviderError("Coinbase cursor outside requested window")
        end = min(start + 299 * query.timeframe.duration, query.end)
        params = urlencode(
            {"start": start.isoformat(), "end": end.isoformat(), "granularity": granularity}
        )
        try:
            body, received_at = self.client.get(
                f"https://api.exchange.coinbase.com/products/{mapping.instrument_id}/candles?{params}"
            )
            payload = json.loads(body, parse_float=Decimal)
            if not isinstance(payload, list) or len(payload) > 300:
                raise ProviderError("Coinbase candle document shape/limit invalid")
            records = []
            for row in payload:
                if not isinstance(row, list) or len(row) != 6 or type(row[0]) is not int:
                    raise ProviderError("Coinbase candle row malformed")
                opened = datetime.fromtimestamp(row[0], UTC)
                if not start <= opened < end:
                    continue  # Endpoint may include earlier/end buckets; do not overlap pages.
                candle = Candle(
                    market_id=query.market_id,
                    timeframe=query.timeframe,
                    open_time=opened,
                    close_time=opened + query.timeframe.duration,
                    low=row[1],
                    high=row[2],
                    open=row[3],
                    close=row[4],
                    volume=row[5],
                    source=self.source,
                    received_at=received_at,
                )
                records.append(candle)
            records.sort(key=lambda c: c.open_time)
            return CandlePage(
                tuple(c.model_dump() for c in records), end.isoformat() if end < query.end else None
            )
        except (PublicDataError, ValueError, OverflowError) as error:
            raise ProviderError("Coinbase historical data unavailable or invalid") from error
