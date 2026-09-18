"""Native Binance Spot adapter. Foundation permits reads, never native submissions."""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pocket_alpha.broker_readonly.binance import (
    PERMISSION_KEYS,
    WRITE_FLAGS,
    NoRedirect,
    amount,
    check_permissions,
    integer,
    milliseconds,
    unique_object,
)
from pocket_alpha.broker_readonly.models import account_hash
from pocket_alpha.common.clock import Clock, SystemClock, utc
from pocket_alpha.config import Settings
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.spot_execution.models import BrokerReport, Commission, SpotPolicy, SpotRequest


class NativeError(Exception):
    pass


class SpotCredentials(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_BINANCE_SPOT_", frozen=True, extra="forbid")
    api_key: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    api_secret: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    expected_uid: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)


class OrderPlan(DomainModel):
    client_id: str = Field(pattern=r"^pa[0-9a-f]{32}$")
    symbol: str = Field(pattern=r"^[A-Z0-9]{1,24}$")
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    price: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    order_type: Literal["LIMIT"] = "LIMIT"
    time_in_force: Literal["GTC"] = "GTC"
    live_trading_enabled: Literal[False] = False

    def parameters(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "timeInForce": self.time_in_force,
            "quantity": format(self.quantity, "f"),
            "price": format(self.price, "f"),
            "newClientOrderId": self.client_id,
            "newOrderRespType": "FULL",
        }


GETS = {
    "/api/v3/time": frozenset(),
    "/api/v3/account": frozenset(),
    "/sapi/v1/account/apiRestrictions": frozenset(),
    "/api/v3/order": frozenset({"symbol", "origClientOrderId"}),
    "/api/v3/myTrades": frozenset({"symbol", "orderId", "fromId", "limit"}),
}
POST_KEYS = frozenset(
    {
        "symbol",
        "side",
        "type",
        "timeInForce",
        "quantity",
        "price",
        "newClientOrderId",
        "newOrderRespType",
    }
)


class Transport(Protocol):
    def send(self, request: Request, timeout: float, maximum_bytes: int) -> bytes: ...


class NativeTransport:
    def send(self, request: Request, timeout: float, maximum_bytes: int) -> bytes:
        parsed = urlsplit(request.full_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.binance.com"
            or parsed.path not in GETS
        ):
            raise NativeError("ENDPOINT_NOT_ALLOWED")
        if request.get_method() == "POST":
            if parsed.path != "/api/v3/order" or not Settings().live_trading_enabled:
                raise NativeError("FOUNDATION_LIVE_DISABLED")
        elif request.get_method() != "GET":
            raise NativeError("ENDPOINT_NOT_ALLOWED")
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            if response.status != 200:
                raise NativeError("BROKER_HTTP_FAILURE")
            body: bytes = response.read(maximum_bytes + 1)
            return body


class BinanceSpotBroker:
    origin: Literal["REAL", "SYNTHETIC"] = "REAL"

    def __init__(
        self,
        policy: SpotPolicy,
        *,
        credentials: SpotCredentials | None = None,
        transport: Transport | None = None,
        clock: Clock | None = None,
        maximum_pages: int = 10,
    ) -> None:
        if not 1 <= maximum_pages <= 20:
            raise ValueError("invalid native page limit")
        self.origin = "REAL" if transport is None else "SYNTHETIC"
        self.policy = SpotPolicy.model_validate_json(policy.model_dump_json())
        self.credentials = credentials or SpotCredentials()
        self.transport = transport or NativeTransport()
        self.clock = clock or SystemClock()
        self.maximum_pages = maximum_pages
        self.last_request: float | None = None
        self.deadline_started: datetime | None = None

    def plan(self, cid: str, request: SpotRequest) -> OrderPlan:
        request = SpotRequest.model_validate_json(request.model_dump_json())
        from pocket_alpha.spot_execution.engine import client_id

        if (
            cid != client_id(request)
            or request.intent.action == "CANCEL"
            or request.intent.quantity is None
        ):
            raise NativeError("INVALID_ORDER_ID_OR_INTENT")
        if (
            request.symbol not in self.policy.symbols
            or request.observation.state.account_identity_hash != self.policy.account_identity_hash
        ):
            raise NativeError("ACCOUNT_OR_SYMBOL_NOT_ALLOWED")
        return OrderPlan(
            client_id=cid,
            symbol=request.symbol,
            side=request.intent.action,
            quantity=request.intent.quantity,
            price=request.limit_price,
        )

    def signed_request(
        self, method: Literal["GET", "POST"], path: str, parameters: Mapping[str, str]
    ) -> Request:
        if method == "GET":
            if path not in GETS or set(parameters) != GETS[path]:
                raise NativeError("ENDPOINT_NOT_ALLOWED")
        elif path != "/api/v3/order" or set(parameters) != POST_KEYS:
            raise NativeError("ENDPOINT_NOT_ALLOWED")
        elif (parameters["type"], parameters["timeInForce"], parameters["newOrderRespType"]) != (
            "LIMIT",
            "GTC",
            "FULL",
        ):
            raise NativeError("UNSUPPORTED_ORDER_TYPE")
        query = dict(parameters)
        headers = {"Accept": "application/json", "User-Agent": "PocketAlpha native spot"}
        if path != "/api/v3/time":
            if (
                not self.credentials.api_key.get_secret_value()
                or not self.credentials.api_secret.get_secret_value()
            ):
                raise NativeError("NATIVE_CREDENTIALS_MISSING")
            delta = utc(self.clock.now()) - datetime(1970, 1, 1, tzinfo=UTC)
            query["timestamp"] = str(
                delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000
            )
            query["recvWindow"] = "5000"
            unsigned = urlencode(query)
            query["signature"] = hmac.new(
                self.credentials.api_secret.get_secret_value().encode(),
                unsigned.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self.credentials.api_key.get_secret_value()
        encoded = urlencode(query)
        url = "https://api.binance.com" + path
        data = None
        if method == "POST":
            data = encoded.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif encoded:
            url += "?" + encoded
        # Ephemeral credential material: never serialize, log or journal this request.
        return Request(url, data=data, headers=headers, method=method)

    def _request(
        self, method: Literal["GET", "POST"], path: str, parameters: Mapping[str, str]
    ) -> Any:
        # Two separate barriers: immutable foundation config and read-only native transport.
        if method == "POST" and not Settings().live_trading_enabled:
            raise NativeError("FOUNDATION_LIVE_DISABLED")
        if self.last_request is not None:
            time.sleep(max(0.0, 0.5 - (time.monotonic() - self.last_request)))
        timeout = 10.0
        if self.deadline_started is not None:
            elapsed = (utc(self.clock.now()) - self.deadline_started).total_seconds()
            remaining = self.policy.maximum_data_age_seconds - elapsed
            if elapsed < 0 or remaining <= 0:
                raise NativeError("QUERY_DEADLINE_EXCEEDED")
            timeout = min(timeout, remaining)
        request = self.signed_request(method, path, parameters)
        self.last_request = time.monotonic()
        try:
            body = self.transport.send(request, timeout, 2_000_000)
            if len(body) > 2_000_000:
                raise ValueError("response limit")
            return json.loads(
                body,
                object_pairs_hook=unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
        except Exception:
            raise NativeError("NATIVE_READ_FAILED") from None

    def qualify(self, *, writing: bool = False) -> dict[str, str | bool]:
        owns_deadline = self.deadline_started is None
        if owns_deadline:
            self.deadline_started = utc(self.clock.now())
        try:
            uid = self.credentials.expected_uid.get_secret_value()
            if (
                not re.fullmatch(r"[0-9]{1,30}", uid)
                or account_hash(uid) != self.policy.account_identity_hash
            ):
                raise NativeError("ACCOUNT_BINDING_INVALID")
            server = milliseconds(self._request("GET", "/api/v3/time", {})["serverTime"])
            if abs((utc(self.clock.now()) - server).total_seconds()) > 5:
                raise NativeError("SERVER_CLOCK_SKEW")
            scopes = self._request("GET", "/sapi/v1/account/apiRestrictions", {})
            if writing:
                if (
                    not isinstance(scopes, dict)
                    or set(scopes) != PERMISSION_KEYS
                    or any(type(scopes[x]) is not bool for x in PERMISSION_KEYS - {"createTime"})
                ):
                    raise NativeError("UNKNOWN_TRADING_KEY_PERMISSIONS")
                integer(scopes["createTime"])
                if (
                    not scopes["enableReading"]
                    or scopes["enableSpotAndMarginTrading"] is not True
                    or any(
                        scopes[x] is not False for x in WRITE_FLAGS - {"enableSpotAndMarginTrading"}
                    )
                ):
                    raise NativeError("TRADING_KEY_PERMISSIONS_INVALID")
                permissions = hashlib.sha256(
                    json.dumps(scopes, sort_keys=True).encode()
                ).hexdigest()
            else:
                permissions = check_permissions(scopes)
            account = self._request("GET", "/api/v3/account", {})
            if (
                str(integer(account["uid"])) != uid
                or account["accountType"] != "SPOT"
                or account["permissions"] != ["SPOT"]
            ):
                raise NativeError("ACCOUNT_IDENTITY_MISMATCH")
            if self._request("GET", "/sapi/v1/account/apiRestrictions", {}) != scopes:
                raise NativeError("PERMISSIONS_CHANGED_DURING_QUALIFICATION")
            if (
                self.deadline_started is not None
                and not 0
                <= (utc(self.clock.now()) - self.deadline_started).total_seconds()
                <= self.policy.maximum_data_age_seconds
            ):
                raise NativeError("QUERY_DEADLINE_EXCEEDED")
            return {
                "account_identity_hash": self.policy.account_identity_hash,
                "permissions_hash": permissions,
                "read_only_qualified": not writing and isinstance(self.transport, NativeTransport),
                "contract_validated": True,
                "live_trading_enabled": False,
                "execution_authorized": False,
                "acquisition": "NATIVE"
                if isinstance(self.transport, NativeTransport)
                else "INJECTED",
            }
        except NativeError:
            raise
        except Exception:
            raise NativeError("NATIVE_QUALIFICATION_INVALID") from None
        finally:
            if owns_deadline:
                self.deadline_started = None

    def submit(self, cid: str, request: SpotRequest) -> BrokerReport:
        plan = self.plan(cid, request)
        if not Settings().live_trading_enabled:
            raise NativeError("FOUNDATION_LIVE_DISABLED")
        from pocket_alpha.spot_execution.risk import evaluate

        decision = evaluate(request, self.policy, now=utc(self.clock.now()), broker_origin="REAL")
        if not decision.submission_permitted or not decision.execution_authorized:
            raise NativeError("NATIVE_RISK_AUTHORIZATION_MISSING")
        self.qualify(writing=True)
        data = self._request("POST", "/api/v3/order", plan.parameters())
        # FULL responses must contain the actual fill fees; a missing field is indeterminate.
        try:
            fees: dict[str, Decimal] = {}
            executed = Decimal(0)
            with localcontext() as context:
                context.prec = 80
                for fill in data["fills"]:
                    executed += amount(fill["qty"])
                    asset = fill["commissionAsset"]
                    fees[asset] = fees.get(asset, Decimal(0)) + amount(fill["commission"])
            report = BrokerReport(
                client_id=data["clientOrderId"],
                symbol=data["symbol"],
                side=plan.side,
                order_id=str(integer(data["orderId"])),
                status=data["status"],
                original_quantity=amount(data["origQty"]),
                limit_price=amount(data["price"]),
                executed_quantity=amount(data["executedQty"]),
                cumulative_quote=amount(data["cummulativeQuoteQty"]),
                commissions=tuple(Commission(asset=k, amount=v) for k, v in sorted(fees.items())),
                at=milliseconds(data["transactTime"]),
            )
            if executed != report.executed_quantity:
                raise NativeError("SUBMISSION_FILL_HISTORY_INCOMPLETE")
            return report
        except Exception:
            raise NativeError("SUBMISSION_RESULT_UNKNOWN") from None

    def query(self, cid: str, symbol: str) -> BrokerReport | None:
        started = utc(self.clock.now())
        self.deadline_started = started
        try:
            if not re.fullmatch(r"pa[0-9a-f]{32}", cid) or symbol not in self.policy.symbols:
                raise NativeError("ORDER_QUERY_NOT_ALLOWED")
            qualification = self.qualify()
            data = self._request(
                "GET", "/api/v3/order", {"symbol": symbol, "origClientOrderId": cid}
            )
            if (
                data["clientOrderId"] != cid
                or data["symbol"] != symbol
                or data["type"] != "LIMIT"
                or data["timeInForce"] != "GTC"
            ):
                raise NativeError("ORDER_IDENTITY_MISMATCH")
            quantity = amount(data["executedQty"])
            quote = amount(data["cummulativeQuoteQty"])
            order_id = integer(data["orderId"])
            fees: dict[str, Decimal] = {}
            executed = cumulative = Decimal(0)
            cursor = 0
            if quantity > 0:
                with localcontext() as context:
                    context.prec = 80
                    for _ in range(self.maximum_pages):
                        page = self._request(
                            "GET",
                            "/api/v3/myTrades",
                            {
                                "symbol": symbol,
                                "orderId": str(order_id),
                                "fromId": str(cursor),
                                "limit": "1000",
                            },
                        )
                        if not isinstance(page, list) or len(page) > 1000:
                            raise NativeError("INVALID_TRADE_PAGE")
                        for trade in page:
                            tid = integer(trade["id"])
                            if (
                                tid < cursor
                                or trade["symbol"] != symbol
                                or integer(trade["orderId"]) != order_id
                                or type(trade["isBuyer"]) is not bool
                                or trade["isBuyer"] != (data["side"] == "BUY")
                            ):
                                raise NativeError("TRADE_IDENTITY_OR_CURSOR_MISMATCH")
                            if (
                                amount(trade["qty"]) <= 0
                                or amount(trade["price"]) <= 0
                                or amount(trade["quoteQty"]) <= 0
                                or milliseconds(trade["time"]) > utc(self.clock.now())
                            ):
                                raise NativeError("INVALID_TRADE_ECONOMICS_OR_TIME")
                            cursor = tid + 1
                            executed += amount(trade["qty"])
                            cumulative += amount(trade["quoteQty"])
                            asset = trade["commissionAsset"]
                            fees[asset] = fees.get(asset, Decimal(0)) + amount(trade["commission"])
                        if len(page) < 1000:
                            break
                    else:
                        raise NativeError("TRADE_PAGE_BUDGET_EXCEEDED")
                if (executed, cumulative) != (quantity, quote):
                    raise NativeError("TRADE_HISTORY_INCOMPLETE")
            bookend = self._request(
                "GET", "/api/v3/order", {"symbol": symbol, "origClientOrderId": cid}
            )
            if bookend != data:
                raise NativeError("ORDER_CHANGED_DURING_QUERY")
            if (
                check_permissions(self._request("GET", "/sapi/v1/account/apiRestrictions", {}))
                != qualification["permissions_hash"]
            ):
                raise NativeError("PERMISSIONS_CHANGED_DURING_QUERY")
            completed = utc(self.clock.now())
            if (
                not 0
                <= (completed - started).total_seconds()
                <= self.policy.maximum_data_age_seconds
            ):
                raise NativeError("QUERY_DEADLINE_EXCEEDED")
            report = BrokerReport(
                client_id=cid,
                symbol=symbol,
                side=data["side"],
                order_id=str(order_id),
                status=data["status"],
                original_quantity=amount(data["origQty"]),
                limit_price=amount(data["price"]),
                executed_quantity=quantity,
                cumulative_quote=quote,
                commissions=tuple(Commission(asset=k, amount=v) for k, v in sorted(fees.items())),
                at=milliseconds(data["updateTime"]),
            )
            if report.at > completed:
                raise NativeError("FUTURE_ORDER_REPORT")
            return report
        except NativeError:
            raise
        except Exception:
            raise NativeError("NATIVE_ORDER_STATE_UNAVAILABLE") from None
        finally:
            self.deadline_started = None
