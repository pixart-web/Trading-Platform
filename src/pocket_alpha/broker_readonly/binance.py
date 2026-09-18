"""Bounded Binance Spot GET adapter. No order, transfer or withdrawal endpoints."""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any, Literal, Protocol
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pocket_alpha.broker_readonly.models import (
    AccountState,
    Balance,
    HistoryScope,
    Instrument,
    InstrumentBinding,
    Observation,
    OpenOrder,
    Trade,
    account_hash,
)
from pocket_alpha.common.clock import Clock, SystemClock, utc


class ReadOnlyError(Exception):
    """Sanitized error: never includes an upstream message, request or credentials."""


class Credentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PA_BINANCE_READONLY_", frozen=True, extra="forbid"
    )
    api_key: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    api_secret: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    expected_uid: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)


PUBLIC = {"/api/v3/time": frozenset(), "/api/v3/exchangeInfo": frozenset({"symbols"})}
PRIVATE = {
    "/sapi/v1/account/apiRestrictions": frozenset(),
    "/api/v3/account": frozenset(),
    "/api/v3/openOrders": frozenset(),
    "/api/v3/myTrades": frozenset({"symbol", "fromId", "limit"}),
}
WRITE_FLAGS = frozenset(
    {
        "enableWithdrawals",
        "enableInternalTransfer",
        "enableMargin",
        "enableFutures",
        "permitsUniversalTransfer",
        "enableVanillaOptions",
        "enableFixApiTrade",
        "enableSpotAndMarginTrading",
        "enablePortfolioMarginTrading",
    }
)
PERMISSION_KEYS = WRITE_FLAGS | {"enableReading", "ipRestrict", "createTime", "enableFixReadOnly"}


class Transport(Protocol):
    def get(
        self, url: str, headers: Mapping[str, str], timeout: float, maximum_bytes: int
    ) -> bytes: ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class NativeTransport:
    def get(
        self, url: str, headers: Mapping[str, str], timeout: float, maximum_bytes: int
    ) -> bytes:
        # Disable ambient proxies and redirects so credentials never move to another origin.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(
            Request(url, headers=dict(headers), method="GET"), timeout=timeout
        ) as response:
            if response.status != 200:
                raise ReadOnlyError("BROKER_HTTP_FAILURE")
            body: bytes = response.read(maximum_bytes + 1)
            return body


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def payload_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def amount(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise ReadOnlyError("INVALID_MONETARY_VALUE")
    number = Decimal(value)
    if not number.is_finite():
        raise ReadOnlyError("INVALID_MONETARY_VALUE")
    return number


def integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ReadOnlyError("INVALID_INTEGER")
    return value


def milliseconds(value: Any) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=integer(value))


def check_permissions(value: Any) -> str:
    if not isinstance(value, dict) or set(value) != PERMISSION_KEYS:
        raise ReadOnlyError("UNKNOWN_KEY_PERMISSIONS")
    if any(type(value[x]) is not bool for x in PERMISSION_KEYS - {"createTime"}):
        raise ReadOnlyError("INVALID_KEY_PERMISSIONS")
    integer(value["createTime"])
    if value["enableReading"] is not True or any(value[x] is not False for x in WRITE_FLAGS):
        raise ReadOnlyError("KEY_NOT_READ_ONLY")
    return payload_hash(value)


class BinanceSpotReader:
    def __init__(
        self,
        credentials: Credentials,
        *,
        transport: Transport | None = None,
        clock: Clock | None = None,
        maximum_pages: int = 10,
        page_size: int = 1000,
        maximum_span_seconds: int = 30,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not 1 <= maximum_pages <= 20
            or not 1 <= page_size <= 1000
            or not 1 <= maximum_span_seconds <= 300
        ):
            raise ValueError("invalid read-only observation bounds")
        if not all(
            x.get_secret_value().strip() for x in (credentials.api_key, credentials.api_secret)
        ):
            raise ReadOnlyError("EMPTY_CREDENTIALS")
        if not re.fullmatch(r"[0-9]{1,30}", credentials.expected_uid.get_secret_value()):
            raise ReadOnlyError("INVALID_ACCOUNT_BINDING")
        self.credentials = credentials
        self.transport = transport or NativeTransport()
        self.origin: Literal["REAL", "SYNTHETIC"] = "REAL" if transport is None else "SYNTHETIC"
        self.clock = clock or SystemClock()
        self.maximum_pages, self.page_size = maximum_pages, page_size
        self.maximum_span_seconds = maximum_span_seconds
        self.sleep, self.monotonic = sleep, monotonic
        self.last_request: float | None = None
        self.started_at: datetime | None = None

    def _get(self, path: str, parameters: Mapping[str, str] | None = None) -> Any:
        parameters = parameters or {}
        allowed = PUBLIC | PRIVATE
        if path not in allowed or set(parameters) != allowed[path]:
            raise ReadOnlyError("ENDPOINT_OR_PARAMETERS_NOT_ALLOWED")
        if self.last_request is not None:
            self.sleep(max(0.0, 0.5 - (self.monotonic() - self.last_request)))
        now = utc(self.clock.now())
        if (
            self.started_at is not None
            and not 0 <= (now - self.started_at).total_seconds() <= self.maximum_span_seconds
        ):
            raise ReadOnlyError("OBSERVATION_DEADLINE_EXCEEDED")
        query = dict(parameters)
        headers = {"Accept": "application/json", "User-Agent": "PocketAlpha read-only"}
        if path in PRIVATE:
            query["timestamp"] = str(
                int((now - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds() * 1000)
            )
            query["recvWindow"] = "5000"
            encoded = urlencode(query)
            query["signature"] = hmac.new(
                self.credentials.api_secret.get_secret_value().encode(),
                encoded.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self.credentials.api_key.get_secret_value()
        url = "https://api.binance.com" + path
        if query:
            url += "?" + urlencode(query)
        self.last_request = self.monotonic()
        try:
            body = self.transport.get(url, headers, 10, 2_000_000)
            if len(body) > 2_000_000:
                raise ReadOnlyError("BROKER_RESPONSE_TOO_LARGE")
            return json.loads(
                body,
                object_pairs_hook=unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
        except Exception:
            raise ReadOnlyError("BROKER_READ_FAILED") from None

    def _account(self) -> tuple[Balance, ...]:
        data = self._get("/api/v3/account")
        uid = str(integer(data["uid"]))
        if uid != self.credentials.expected_uid.get_secret_value():
            raise ReadOnlyError("ACCOUNT_IDENTITY_MISMATCH")
        if data["accountType"] != "SPOT" or data["permissions"] != ["SPOT"]:
            raise ReadOnlyError("UNSUPPORTED_ACCOUNT_TYPE")
        # canTrade/canWithdraw describe the account, not the API key's scopes.
        balances = tuple(
            Balance(asset=x["asset"], free=amount(x["free"]), locked=amount(x["locked"]))
            for x in data["balances"]
        )
        if len({x.asset for x in balances}) != len(balances):
            raise ReadOnlyError("DUPLICATE_BALANCE")
        return tuple(sorted(balances, key=lambda x: x.asset))

    def _orders(self, symbols: set[str]) -> tuple[OpenOrder, ...]:
        result = tuple(
            OpenOrder(
                symbol=x["symbol"],
                order_id=integer(x["orderId"]),
                client_order_id=x["clientOrderId"],
                side=x["side"],
                order_type=x["type"],
                status=x["status"],
                quantity=amount(x["origQty"]),
                executed_quantity=amount(x["executedQty"]),
                price=amount(x["price"]),
                venue_payload_hash=payload_hash(x),
            )
            for x in self._get("/api/v3/openOrders")
        )
        if any(x.symbol not in symbols for x in result):
            raise ReadOnlyError("OPEN_ORDER_OUTSIDE_SCOPE")
        if len({(x.symbol, x.order_id) for x in result}) != len(result):
            raise ReadOnlyError("DUPLICATE_ORDER")
        return tuple(sorted(result, key=lambda x: (x.symbol, x.order_id)))

    def _history(self, scope: HistoryScope, quote_precision: int = 8) -> tuple[Trade, ...]:
        cursor = scope.from_id
        result: list[Trade] = []
        for _ in range(self.maximum_pages):
            page = self._get(
                "/api/v3/myTrades",
                {"symbol": scope.symbol, "fromId": str(cursor), "limit": str(self.page_size)},
            )
            if not isinstance(page, list) or len(page) > self.page_size:
                raise ReadOnlyError("INVALID_HISTORY_PAGE")
            for x in page:
                trade_id = integer(x["id"])
                if (
                    x["symbol"] != scope.symbol
                    or trade_id < cursor
                    or type(x["isBuyer"]) is not bool
                ):
                    raise ReadOnlyError("HISTORY_CURSOR_OR_SYMBOL_MISMATCH")
                if result and trade_id <= result[-1].trade_id:
                    raise ReadOnlyError("HISTORY_NOT_STRICTLY_ORDERED")
                result.append(
                    Trade(
                        symbol=x["symbol"],
                        trade_id=trade_id,
                        order_id=integer(x["orderId"]),
                        side="BUY" if x["isBuyer"] else "SELL",
                        quantity=amount(x["qty"]),
                        price=amount(x["price"]),
                        quote_quantity=amount(x["quoteQty"]),
                        commission=amount(x["commission"]),
                        commission_asset=x["commissionAsset"],
                        occurred_at=milliseconds(x["time"]),
                        venue_payload_hash=payload_hash(x),
                    )
                )
            with localcontext() as context:
                context.prec = 80
                quantum = Decimal(1).scaleb(-quote_precision)
                if any(abs(x.price * x.quantity - x.quote_quantity) > quantum for x in result):
                    raise ReadOnlyError("TRADE_QUOTE_VALUE_INCONSISTENT")
            if len(page) < self.page_size:
                return tuple(result)
            cursor = result[-1].trade_id + 1
        raise ReadOnlyError("HISTORY_PAGE_BUDGET_EXHAUSTED")

    def observe(
        self, bindings: tuple[InstrumentBinding, ...], scopes: tuple[HistoryScope, ...]
    ) -> Observation:
        self.started_at = utc(self.clock.now())
        try:
            symbols = {x.symbol for x in bindings}
            if not 1 <= len(bindings) <= 10 or len(symbols) != len(bindings):
                raise ReadOnlyError("INVALID_INSTRUMENT_SCOPE")
            if {x.symbol for x in scopes} != symbols or len(scopes) != len(symbols):
                raise ReadOnlyError("INVALID_HISTORY_SCOPE")
            server = milliseconds(self._get("/api/v3/time")["serverTime"])
            if abs((utc(self.clock.now()) - server).total_seconds()) > 5:
                raise ReadOnlyError("SERVER_CLOCK_SKEW")
            permissions = check_permissions(self._get("/sapi/v1/account/apiRestrictions"))
            balances = self._account()
            orders = self._orders(symbols)
            metadata = self._get(
                "/api/v3/exchangeInfo",
                {"symbols": json.dumps(sorted(symbols), separators=(",", ":"))},
            )
            by_symbol = {x["symbol"]: x for x in metadata["symbols"]}
            if set(by_symbol) != symbols or len(by_symbol) != len(metadata["symbols"]):
                raise ReadOnlyError("INSTRUMENT_METADATA_INCOMPLETE")
            instruments: list[Instrument] = []
            for binding in bindings:
                x = by_symbol[binding.symbol]
                if (x["baseAsset"], x["quoteAsset"]) != (
                    binding.base_asset,
                    binding.quote_asset,
                ) or x["isSpotTradingAllowed"] is not True:
                    raise ReadOnlyError("INSTRUMENT_IDENTITY_MISMATCH")
                filters = {f["filterType"]: f for f in x["filters"]}
                if len(filters) != len(x["filters"]):
                    raise ReadOnlyError("DUPLICATE_INSTRUMENT_FILTER")
                instruments.append(
                    Instrument(
                        symbol=binding.symbol,
                        market_id=binding.market_id,
                        asset_id=binding.asset_id,
                        base_asset=x["baseAsset"],
                        quote_asset=x["quoteAsset"],
                        status=x["status"],
                        price_tick=amount(filters["PRICE_FILTER"]["tickSize"]),
                        quantity_step=amount(filters["LOT_SIZE"]["stepSize"]),
                        quote_asset_precision=integer(x["quoteAssetPrecision"]),
                        metadata_hash=payload_hash(x),
                    )
                )
            trades = tuple(
                trade
                for scope in sorted(scopes, key=lambda x: x.symbol)
                for trade in self._history(
                    scope,
                    next(x.quote_asset_precision for x in instruments if x.symbol == scope.symbol),
                )
            )
            if self._orders(symbols) != orders or self._account() != balances:
                raise ReadOnlyError("ACCOUNT_CHANGED_DURING_OBSERVATION")
            if check_permissions(self._get("/sapi/v1/account/apiRestrictions")) != permissions:
                raise ReadOnlyError("PERMISSIONS_CHANGED_DURING_OBSERVATION")
            state = AccountState(
                origin=self.origin,
                account_identity_hash=account_hash(
                    self.credentials.expected_uid.get_secret_value()
                ),
                instruments=tuple(instruments),
                balances=balances,
                open_orders=orders,
                trades=trades,
                history_scope=scopes,
            ).canonical()
            completed = utc(self.clock.now())
            if not 0 <= (completed - self.started_at).total_seconds() <= self.maximum_span_seconds:
                raise ReadOnlyError("OBSERVATION_DEADLINE_EXCEEDED")
            return Observation(
                state=state,
                started_at=self.started_at,
                completed_at=completed,
                permissions_hash=permissions,
            )
        except ReadOnlyError:
            raise
        except Exception:
            raise ReadOnlyError("BROKER_SCHEMA_OR_STATE_INVALID") from None
        finally:
            self.started_at = None
