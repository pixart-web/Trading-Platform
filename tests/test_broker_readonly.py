"""Synthetic transport fixtures only: no private network or real account/order access."""

import copy
import hashlib
import hmac
import json
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr, ValidationError

from pocket_alpha.broker_readonly.binance import (
    PERMISSION_KEYS,
    PRIVATE,
    PUBLIC,
    WRITE_FLAGS,
    BinanceSpotReader,
    Credentials,
    NativeTransport,
    NoRedirect,
    ReadOnlyError,
    amount,
    check_permissions,
    integer,
)
from pocket_alpha.broker_readonly.cli import main
from pocket_alpha.broker_readonly.models import (
    Balance,
    HistoryScope,
    InstrumentBinding,
    LocalState,
    Observation,
    Reconciliation,
    digest,
    reconcile,
)
from pocket_alpha.common.clock import FrozenClock

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
MS = int(NOW.timestamp() * 1000)
KEY = "synthetic-key-not-a-credential"
SECRET = "synthetic-secret-not-a-credential"
BINDING = InstrumentBinding(
    symbol="BTCUSDT",
    market_id="binance:BTCUSDT",
    asset_id="BTC",
    base_asset="BTC",
    quote_asset="USDT",
)
SCOPE = HistoryScope(symbol="BTCUSDT", from_id=0)


def permissions() -> dict[str, Any]:
    return {
        **{key: False for key in PERMISSION_KEYS},
        "enableReading": True,
        "ipRestrict": True,
        "createTime": MS - 1000,
    }


def trade(trade_id: int = 7) -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "id": trade_id,
        "orderId": 12,
        "price": "20000",
        "qty": "0.01",
        "quoteQty": "200",
        "commission": "0.0001",
        "commissionAsset": "BNB",
        "time": MS - 1000,
        "isBuyer": True,
        "isMaker": False,
    }


def order() -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "orderId": 13,
        "clientOrderId": "external-13",
        "side": "BUY",
        "type": "LIMIT",
        "status": "PARTIALLY_FILLED",
        "origQty": "0.02",
        "executedQty": "0.01",
        "price": "20000",
        "stopPrice": "0",
        "time": MS - 2000,
    }


class FakeTransport:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {
            "/api/v3/time": {"serverTime": MS},
            "/sapi/v1/account/apiRestrictions": permissions(),
            "/api/v3/account": {
                "uid": 42,
                "accountType": "SPOT",
                "permissions": ["SPOT"],
                "canTrade": True,
                "canWithdraw": True,
                "canDeposit": True,
                "balances": [
                    {"asset": "BTC", "free": "0.01", "locked": "0.01"},
                    {"asset": "USDT", "free": "1000", "locked": "200"},
                ],
            },
            "/api/v3/openOrders": [order()],
            "/api/v3/exchangeInfo": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "quoteAssetPrecision": 8,
                        "status": "TRADING",
                        "isSpotTradingAllowed": True,
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                        ],
                    }
                ]
            },
            "/api/v3/myTrades": [trade()],
        }
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.pages: list[Any] | None = None
        self.second: dict[str, Any] = {}
        self.counts: dict[str, int] = {}
        self.failure: Exception | None = None
        self.body: bytes | None = None

    def get(
        self, url: str, headers: Mapping[str, str], timeout: float, maximum_bytes: int
    ) -> bytes:
        assert urlsplit(url).scheme == "https"
        assert urlsplit(url).netloc == "api.binance.com"
        assert timeout == 10 and maximum_bytes == 2_000_000
        path = urlsplit(url).path
        self.calls.append((url, dict(headers)))
        self.counts[path] = self.counts.get(path, 0) + 1
        if self.failure:
            raise self.failure
        if self.body is not None:
            return self.body
        if path == "/api/v3/myTrades" and self.pages is not None:
            value = self.pages.pop(0)
        elif self.counts[path] > 1 and path in self.second:
            value = self.second[path]
        else:
            value = self.data[path]
        return json.dumps(value).encode()


def reader(transport: FakeTransport, **kwargs: Any) -> BinanceSpotReader:
    return BinanceSpotReader(
        Credentials(
            api_key=SecretStr(KEY), api_secret=SecretStr(SECRET), expected_uid=SecretStr("42")
        ),
        transport=transport,
        clock=FrozenClock(NOW),
        sleep=lambda _: None,
        **kwargs,
    )


def observe(transport: FakeTransport | None = None) -> Observation:
    return reader(transport or FakeTransport()).observe((BINDING,), (SCOPE,))


def local(observation: Observation) -> LocalState:
    return LocalState(
        state=observation.state,
        revision=1,
        recorded_at=NOW - timedelta(seconds=1),
        independently_verified=True,
    )


def test_capture_and_signing_no_execution() -> None:
    transport = FakeTransport()
    observation = observe(transport)
    assert observation.state.origin == "SYNTHETIC"
    assert observation.state.balances[0].spot_position_quantity == Decimal("0.02")
    assert observation.state.trades[0].commission_asset == "BNB"
    assert observation.state.trades[0].quote_quantity == Decimal("200")
    assert not observation.execution_authorized and not observation.live_trading_enabled
    assert observation.completed_at == NOW
    for url, headers in transport.calls:
        path = urlsplit(url).path
        assert path in PUBLIC | PRIVATE
        query = parse_qs(urlsplit(url).query)
        if path in PRIVATE:
            encoded = urlsplit(url).query.rsplit("&signature=", 1)[0]
            expected = hmac.new(SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
            assert query["signature"] == [expected]
            assert query["timestamp"] == [str(MS)] and query["recvWindow"] == ["5000"]
            assert headers["X-MBX-APIKEY"] == KEY
        else:
            assert "X-MBX-APIKEY" not in headers
    assert len(transport.calls) == 9
    assert SECRET not in observation.model_dump_json() and KEY not in observation.model_dump_json()
    assert '"42"' not in observation.model_dump_json()


@pytest.mark.parametrize("flag", sorted(WRITE_FLAGS))
def test_every_write_permission_rejected_before_account_access(flag: str) -> None:
    transport = FakeTransport()
    transport.data["/sapi/v1/account/apiRestrictions"][flag] = True
    with pytest.raises(ReadOnlyError, match="KEY_NOT_READ_ONLY"):
        observe(transport)
    assert "/api/v3/account" not in transport.counts


@pytest.mark.parametrize("mutation", ["missing", "unknown", "not_bool", "no_read", "bad_time"])
def test_permissions_fail_closed(mutation: str) -> None:
    value = permissions()
    if mutation == "missing":
        value.pop("enableFixApiTrade")
    elif mutation == "unknown":
        value["newPrivilege"] = False
    elif mutation == "not_bool":
        value["enableWithdrawals"] = 0
    elif mutation == "no_read":
        value["enableReading"] = False
    else:
        value["createTime"] = True
    with pytest.raises(ReadOnlyError):
        check_permissions(value)


@pytest.mark.parametrize(
    "path,parameters",
    [
        ("/api/v3/order", {}),
        ("/sapi/v1/capital/withdraw/apply", {}),
        ("/api/v3/account", {"unexpected": "true"}),
        ("https://evil.invalid", {}),
    ],
)
def test_transport_allowlist(path: str, parameters: dict[str, str]) -> None:
    transport = FakeTransport()
    with pytest.raises(ReadOnlyError, match="NOT_ALLOWED"):
        reader(transport)._get(path, parameters)
    assert not transport.calls


@pytest.mark.parametrize(
    "case",
    [
        "uid",
        "account",
        "permissions",
        "balance_duplicate",
        "negative",
        "float",
        "order_unknown",
        "order_excess",
        "order_duplicate",
        "order_outside",
        "metadata_missing",
        "metadata_duplicate",
        "asset_mismatch",
        "spot_disabled",
        "halted",
        "filter_duplicate",
        "bad_tick",
        "future_trade",
        "wrong_trade_symbol",
        "bad_trade_id",
        "bad_buyer",
        "trade_duplicate",
        "trade_order",
    ],
)
def test_unknown_and_inconsistent_state_rejected(case: str) -> None:
    transport = FakeTransport()
    account = transport.data["/api/v3/account"]
    orders = transport.data["/api/v3/openOrders"]
    symbol = transport.data["/api/v3/exchangeInfo"]["symbols"][0]
    trades = transport.data["/api/v3/myTrades"]
    if case == "uid":
        account["uid"] = 43
    elif case == "account":
        account["accountType"] = "MARGIN"
    elif case == "permissions":
        account["permissions"] = ["SPOT", "MARGIN"]
    elif case == "balance_duplicate":
        account["balances"].append(account["balances"][0])
    elif case == "negative":
        account["balances"][0]["free"] = "-1"
    elif case == "float":
        account["balances"][0]["free"] = 0.01
    elif case == "order_unknown":
        orders[0]["status"] = "UNKNOWN"
    elif case == "order_excess":
        orders[0]["executedQty"] = "1"
    elif case == "order_duplicate":
        orders.append(orders[0])
    elif case == "order_outside":
        orders[0]["symbol"] = "ETHUSDT"
    elif case == "metadata_missing":
        transport.data["/api/v3/exchangeInfo"]["symbols"] = []
    elif case == "metadata_duplicate":
        transport.data["/api/v3/exchangeInfo"]["symbols"].append(symbol)
    elif case == "asset_mismatch":
        symbol["baseAsset"] = "ETH"
    elif case == "spot_disabled":
        symbol["isSpotTradingAllowed"] = False
    elif case == "halted":
        symbol["status"] = "BREAK"
    elif case == "filter_duplicate":
        symbol["filters"].append(symbol["filters"][0])
    elif case == "bad_tick":
        symbol["filters"][0]["tickSize"] = "0"
    elif case == "future_trade":
        trades[0]["time"] = MS + 1000
    elif case == "wrong_trade_symbol":
        trades[0]["symbol"] = "ETHUSDT"
    elif case == "bad_trade_id":
        trades[0]["id"] = True
    elif case == "bad_buyer":
        trades[0]["isBuyer"] = 1
    elif case == "trade_duplicate":
        trades.append(trades[0])
    else:
        trades.extend([trade(9), trade(8)])
    with pytest.raises(ReadOnlyError):
        observe(transport)


@pytest.mark.parametrize(
    "path", ["/api/v3/account", "/api/v3/openOrders", "/sapi/v1/account/apiRestrictions"]
)
def test_state_change_between_bookends(path: str) -> None:
    transport = FakeTransport()
    changed = copy.deepcopy(transport.data[path])
    if path == "/api/v3/account":
        changed["balances"][0]["free"] = "0.02"
    elif path == "/api/v3/openOrders":
        changed[0]["stopPrice"] = "19000"
    else:
        changed["ipRestrict"] = False
    transport.second[path] = changed
    with pytest.raises(ReadOnlyError, match="CHANGED_DURING_OBSERVATION"):
        observe(transport)


def test_history_pagination_cursor_and_budget() -> None:
    transport = FakeTransport()
    transport.pages = [[trade(7), trade(9)], [trade(15)]]
    observation = reader(transport, page_size=2).observe((BINDING,), (SCOPE,))
    assert [x.trade_id for x in observation.state.trades] == [7, 9, 15]
    urls = [url for url, _ in transport.calls if urlsplit(url).path == "/api/v3/myTrades"]
    assert parse_qs(urlsplit(urls[1]).query)["fromId"] == ["10"]
    transport = FakeTransport()
    with pytest.raises(ReadOnlyError, match="BUDGET_EXHAUSTED"):
        reader(transport, page_size=1, maximum_pages=1).observe((BINDING,), (SCOPE,))


@pytest.mark.parametrize("page", [{}, [trade(), trade(8)], [{**trade(), "id": 0}]])
def test_history_invalid_page_or_cursor(page: Any) -> None:
    transport = FakeTransport()
    transport.pages = [page]
    with pytest.raises(ReadOnlyError):
        reader(transport, page_size=1)._history(HistoryScope(symbol="BTCUSDT", from_id=5))


def test_clock_skew_and_deadline() -> None:
    transport = FakeTransport()
    transport.data["/api/v3/time"]["serverTime"] = MS - 6000
    with pytest.raises(ReadOnlyError, match="CLOCK_SKEW"):
        observe(transport)
    instance = reader(FakeTransport())
    instance.started_at = NOW - timedelta(seconds=31)
    with pytest.raises(ReadOnlyError, match="DEADLINE"):
        instance._get("/api/v3/time")
    instance.started_at = NOW + timedelta(seconds=1)
    with pytest.raises(ReadOnlyError, match="DEADLINE"):
        instance._get("/api/v3/time")


@pytest.mark.parametrize(
    "body",
    [b'{"x":1,"x":2}', b'{"x":NaN}', b"invalid", b"x" * 2_000_001],
    ids=["duplicate-key", "non-finite", "invalid-json", "oversized"],
)
def test_invalid_response_sanitized(body: bytes) -> None:
    transport = FakeTransport()
    transport.body = body
    with pytest.raises(ReadOnlyError, match="BROKER_READ_FAILED"):
        observe(transport)


def test_upstream_secret_does_not_escape_exception() -> None:
    transport = FakeTransport()
    transport.failure = RuntimeError(KEY + SECRET)
    with pytest.raises(ReadOnlyError) as caught:
        observe(transport)
    rendered = "".join(traceback.format_exception(caught.value))
    assert KEY not in rendered and SECRET not in rendered


def test_credentials_env_only_redacted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PA_BINANCE_READONLY_API_KEY=forbidden-dotenv", encoding="utf-8")
    monkeypatch.setenv("PA_BINANCE_READONLY_API_KEY", KEY)
    monkeypatch.setenv("PA_BINANCE_READONLY_API_SECRET", SECRET)
    monkeypatch.setenv("PA_BINANCE_READONLY_EXPECTED_UID", "42")
    credentials = Credentials()
    assert credentials.api_key.get_secret_value() == KEY
    assert credentials.model_dump() == {} and KEY not in repr(credentials)
    monkeypatch.delenv("PA_BINANCE_READONLY_API_KEY")
    assert Credentials().api_key.get_secret_value() == ""
    with pytest.raises(ReadOnlyError, match="EMPTY_CREDENTIALS"):
        BinanceSpotReader(Credentials())


@pytest.mark.parametrize("value", [True, -1, 1.0, "1", None])
def test_integer_no_coercion(value: Any) -> None:
    with pytest.raises(ReadOnlyError):
        integer(value)


@pytest.mark.parametrize("value", [1.0, "NaN", "Infinity", "-1", "1e-3", " 1", None])
def test_money_no_float_or_unknown(value: Any) -> None:
    with pytest.raises(ReadOnlyError):
        amount(value)


def test_decimal_position_is_independent_of_global_context() -> None:
    balance = Balance(
        asset="BTC",
        free=Decimal("123456789.123456789123456789"),
        locked=Decimal("0.000000000000000001"),
    )
    with localcontext() as context:
        context.prec = 6
        assert balance.spot_position_quantity == Decimal("123456789.123456789123456790")


def test_reconciliation_missing_synthetic_and_exact_state() -> None:
    observation = observe()
    assert reconcile(observation, None, now=NOW).reasons == (
        "NON_REAL_OBSERVATION",
        "LOCAL_STATE_MISSING",
    )
    assert not reconcile(observation, local(observation), now=NOW).read_only_ready
    # Unit-model REAL label exercises the gate; this is not a genuine account observation.
    modeled = observation.model_copy(
        update={"state": observation.state.model_copy(update={"origin": "REAL"})}
    )
    result = reconcile(modeled, local(modeled), now=NOW)
    assert result.status == "MATCHED" and result.read_only_ready
    assert not result.execution_authorized and not result.live_trading_enabled
    assert result.observation_hash == digest(modeled)
    assert result.local_state_hash == digest(local(modeled))
    mutable_view: Any = result
    with pytest.raises(ValidationError):
        mutable_view.live_trading_enabled = True


@pytest.mark.parametrize(
    "field",
    [
        "origin",
        "account_identity_hash",
        "instruments",
        "balances",
        "open_orders",
        "trades",
        "history_scope",
    ],
)
def test_each_reconciliation_component(field: str) -> None:
    observation = observe()
    state = observation.state
    changes: dict[str, Any] = {
        "origin": "REAL",
        "account_identity_hash": "0" * 64,
        "instruments": (state.instruments[0].model_copy(update={"price_tick": Decimal("0.02")}),),
        "balances": (
            state.balances[0].model_copy(update={"locked": Decimal("0")}),
            state.balances[1],
        ),
        "open_orders": (),
        "trades": (),
        "history_scope": (HistoryScope(symbol="BTCUSDT", from_id=1),),
    }
    changed = local(observation).model_copy(
        update={"state": state.model_copy(update={field: changes[field]})}
    )
    assert field.upper() + "_MISMATCH" in reconcile(observation, changed, now=NOW).reasons


def test_reconciliation_time_and_order_independence() -> None:
    observation = observe()
    reordered = local(observation).model_copy(
        update={
            "state": observation.state.model_copy(
                update={"balances": tuple(reversed(observation.state.balances))}
            )
        }
    )
    assert "BALANCES_MISMATCH" not in reconcile(observation, reordered, now=NOW).reasons
    assert (
        "OBSERVATION_NOT_CURRENT"
        in reconcile(observation, reordered, now=NOW + timedelta(seconds=31)).reasons
    )
    assert (
        "OBSERVATION_NOT_CURRENT"
        in reconcile(observation, reordered, now=NOW - timedelta(seconds=1)).reasons
    )
    future = reordered.model_copy(update={"recorded_at": NOW + timedelta(seconds=1)})
    assert "LOCAL_STATE_NOT_CAUSAL" in reconcile(observation, future, now=NOW).reasons
    extended = observation.model_copy(update={"started_at": NOW - timedelta(seconds=31)})
    assert "OBSERVATION_SPAN_EXCEEDED" in reconcile(extended, reordered, now=NOW).reasons
    with pytest.raises(ValueError):
        reconcile(observation, reordered, now=NOW, maximum_age_seconds=0)


@pytest.mark.parametrize(
    "change", ["balance", "order", "trade", "scope", "instrument", "market", "outside"]
)
def test_state_schema_uniqueness_and_scope(change: str) -> None:
    state = observe().state
    data = state.model_dump()
    if change == "balance":
        data["balances"] += (data["balances"][0],)
    elif change == "order":
        data["open_orders"] += (data["open_orders"][0],)
    elif change == "trade":
        data["trades"] += (data["trades"][0],)
    elif change == "scope":
        data["history_scope"] = ()
    elif change == "instrument":
        data["instruments"] += (data["instruments"][0],)
    elif change == "market":
        data["instruments"] += ({**data["instruments"][0], "symbol": "ETHUSDT"},)
    else:
        data["trades"][0]["symbol"] = "ETHUSDT"
    with pytest.raises(ValidationError):
        type(state).model_validate(data)


def test_schema_rejects_execution_future_and_inconsistent_readiness() -> None:
    observation = observe()
    data = observation.model_dump()
    data["live_trading_enabled"] = True
    with pytest.raises(ValidationError):
        Observation.model_validate(data)
    data = observation.model_dump()
    data["completed_at"] = NOW - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        Observation.model_validate(data)
    result = reconcile(observation, None, now=NOW).model_dump()
    result["read_only_ready"] = True
    with pytest.raises(ValidationError):
        Reconciliation.model_validate(result)
    result.update(status="MATCHED", reasons=(), local_state_hash=None)
    with pytest.raises(ValidationError):
        Reconciliation.model_validate(result)


def test_native_transport_fixed_get_and_redirect_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[RequestLike] = []

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def read(self, size: int) -> bytes:
            assert size == 101
            return b"{}"

    class Opener:
        def open(self, request: Any, timeout: float) -> Response:
            requests.append(request)
            assert request.get_method() == "GET" and timeout == 1
            return Response()

    monkeypatch.setattr("pocket_alpha.broker_readonly.binance.build_opener", lambda *args: Opener())
    assert NativeTransport().get("https://api.binance.com/api/v3/time", {}, 1, 100) == b"{}"
    handler: Any = NoRedirect()
    assert (
        handler.redirect_request(requests[0], None, 302, "redirect", None, "https://evil.invalid")
        is None
    )


RequestLike = Any


def test_cli_no_overwrite_no_network_and_sanitized_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["observe", "--request", str(tmp_path / "request.json"), "--output", str(output)],
    )
    assert main() == 2
    assert output.read_text(encoding="utf-8") == "preserve"
    assert "OUTPUT_ALREADY_EXISTS" in capsys.readouterr().out
    output.unlink()
    assert main() == 2
    assert "CONFIGURATION_OR_IO_FAILED" in capsys.readouterr().out


def test_cli_receipt_blocked_without_local_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"instruments": [BINDING.model_dump()], "history_scope": [SCOPE.model_dump()]}),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"
    observation = observe()
    monkeypatch.setenv("PA_BINANCE_READONLY_API_KEY", KEY)
    monkeypatch.setenv("PA_BINANCE_READONLY_API_SECRET", SECRET)
    monkeypatch.setenv("PA_BINANCE_READONLY_EXPECTED_UID", "42")
    monkeypatch.setattr("sys.argv", ["observe", "--request", str(request), "--output", str(output)])
    monkeypatch.setattr(
        "pocket_alpha.broker_readonly.cli.BinanceSpotReader.observe", lambda *args: observation
    )
    monkeypatch.setattr("pocket_alpha.broker_readonly.cli.SystemClock.now", lambda *args: NOW)
    assert main() == 2
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert "LOCAL_STATE_MISSING" in receipt["reconciliation"]["reasons"]
    assert SECRET not in output.read_text(encoding="utf-8")
    assert capsys.readouterr().out.strip() == "READ_ONLY_BLOCKED"


def test_reported_trade_quote_value_must_be_consistent() -> None:
    transport = FakeTransport()
    transport.data["/api/v3/myTrades"][0]["quoteQty"] = "201"
    with pytest.raises(ReadOnlyError, match="QUOTE_VALUE_INCONSISTENT"):
        observe(transport)
    transport.data["/api/v3/myTrades"][0]["quoteQty"] = "200.00000001"
    assert observe(transport).state.trades[0].quote_quantity == Decimal("200.00000001")


@pytest.mark.parametrize(
    "change",
    [
        {"origQty": "0"},
        {"executedQty": "0.02"},
        {"executedQty": "0"},
        {"status": "NEW"},
        {"price": "0"},
    ],
)
def test_open_order_economics_fail_closed(change: dict[str, str]) -> None:
    transport = FakeTransport()
    transport.data["/api/v3/openOrders"][0].update(change)
    with pytest.raises(ReadOnlyError):
        observe(transport)


@pytest.mark.parametrize(
    "kwargs", [{"maximum_pages": 0}, {"page_size": 1001}, {"maximum_span_seconds": 301}]
)
def test_policy_bounds(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        reader(FakeTransport(), **kwargs)


def test_invalid_account_binding_and_request_scope() -> None:
    with pytest.raises(ReadOnlyError, match="INVALID_ACCOUNT_BINDING"):
        BinanceSpotReader(
            Credentials(
                api_key=SecretStr(KEY), api_secret=SecretStr(SECRET), expected_uid=SecretStr("bad")
            )
        )
    instance = reader(FakeTransport())
    with pytest.raises(ReadOnlyError, match="INVALID_INSTRUMENT_SCOPE"):
        instance.observe((BINDING, BINDING), (SCOPE,))
    with pytest.raises(ReadOnlyError, match="INVALID_HISTORY_SCOPE"):
        instance.observe((BINDING,), ())
