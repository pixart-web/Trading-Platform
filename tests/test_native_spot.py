"""Mock native wire contracts only; no network or real order is executed."""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest
from pydantic import SecretStr

from pocket_alpha.broker_readonly.binance import WRITE_FLAGS
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.spot_execution.binance import (
    BinanceSpotBroker,
    NativeError,
    NativeTransport,
    SpotCredentials,
)
from pocket_alpha.spot_execution.engine import SpotExecution, client_id
from pocket_alpha.spot_execution.qualify import main
from tests.test_broker_readonly import FakeTransport
from tests.test_spot_execution import policy, request

KEY, SECRET = "synthetic-native-key", "synthetic-native-secret"


class Wire:
    def __init__(self, value: Any) -> None:
        at = value.proposal.at
        self.fake = FakeTransport()
        self.fake.data["/api/v3/time"]["serverTime"] = int(at.timestamp() * 1000)
        self.order = {
            "symbol": value.symbol,
            "clientOrderId": client_id(value),
            "orderId": 12,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "status": "NEW",
            "origQty": "0.01",
            "executedQty": "0",
            "price": "106",
            "cummulativeQuoteQty": "0",
            "updateTime": int(at.timestamp() * 1000),
        }
        self.trades: list[dict[str, Any]] = []
        self.calls: list[Request] = []
        self.body: bytes | None = None
        self.failure = False
        self.changed: dict[str, Any] | None = None

    def send(self, req: Request, timeout: float, maximum_bytes: int) -> bytes:
        assert req.get_method() == "GET"
        assert urlsplit(req.full_url).netloc == "api.binance.com"
        assert 0 < timeout <= 10 and maximum_bytes == 2_000_000
        self.calls.append(req)
        if self.failure:
            raise TimeoutError(KEY + SECRET)
        if self.body is not None:
            return self.body
        result: Any
        path = urlsplit(req.full_url).path
        if path == "/api/v3/order":
            count = sum(urlsplit(x.full_url).path == path for x in self.calls)
            result = self.changed if self.changed and count > 1 else self.order
        elif path == "/api/v3/myTrades":
            result = self.trades
        else:
            result = self.fake.data[path]
        return json.dumps(result).encode()


def adapter(value: Any, wire: Wire, **kwargs: Any) -> BinanceSpotBroker:
    return BinanceSpotBroker(
        policy(value),
        credentials=SpotCredentials(
            api_key=SecretStr(KEY), api_secret=SecretStr(SECRET), expected_uid=SecretStr("42")
        ),
        transport=wire,
        clock=FrozenClock(value.proposal.at),
        **kwargs,
    )


def fill(wire: Wire) -> None:
    wire.order.update(status="FILLED", executedQty="0.01", cummulativeQuoteQty="1.06")
    wire.trades = [
        {
            "symbol": "BTCUSDT",
            "orderId": 12,
            "id": 7,
            "isBuyer": True,
            "price": "106",
            "qty": "0.01",
            "quoteQty": "1.06",
            "commission": "0.001",
            "commissionAsset": "BNB",
            "time": wire.order["updateTime"],
        }
    ]


def test_native_plan_and_signed_post_is_never_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    value = request()
    wire = Wire(value)
    broker = adapter(value, wire)
    plan = broker.plan(client_id(value), value)
    encoded = broker.signed_request("POST", "/api/v3/order", plan.parameters())
    assert encoded.get_method() == "POST" and isinstance(encoded.data, bytes)
    body = encoded.data.decode()
    unsigned = body.rsplit("&signature=", 1)[0]
    assert parse_qs(body)["signature"] == [
        hmac.new(SECRET.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
    ]
    assert SECRET not in plan.model_dump_json() and KEY not in plan.model_dump_json()
    with pytest.raises(NativeError, match="FOUNDATION_LIVE_DISABLED"):
        broker.submit(client_id(value), value)
    with pytest.raises(NativeError, match="FOUNDATION_LIVE_DISABLED"):
        broker._request("POST", "/api/v3/order", plan.parameters())
    with pytest.raises(NativeError, match="FOUNDATION_LIVE_DISABLED"):
        NativeTransport().send(encoded, 1, 100)
    assert not wire.calls


def test_native_new_and_actual_fee_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pocket_alpha.spot_execution.binance.time.sleep", lambda _: None)
    value = request()
    wire = Wire(value)
    broker = adapter(value, wire)
    report = broker.query(client_id(value), value.symbol)
    assert report is not None and report.status == "NEW" and report.commissions == ()
    fill(wire)
    wire.calls.clear()
    report = broker.query(client_id(value), value.symbol)
    assert report is not None and report.executed_quantity == D("0.01")
    assert report.commissions[0].asset == "BNB" and report.commissions[0].amount == D("0.001")
    assert broker.deadline_started is None


@pytest.mark.parametrize(
    "case",
    [
        "uid",
        "clock",
        "permissions",
        "identity",
        "missing_history",
        "duplicate",
        "future_trade",
        "bad_qty",
        "order_changed",
        "quote_unavailable",
    ],
)
def test_native_unknown_state_fails_closed(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pocket_alpha.spot_execution.binance.time.sleep", lambda _: None)
    value = request()
    wire = Wire(value)
    fill(wire)
    if case == "uid":
        wire.fake.data["/api/v3/account"]["uid"] = 43
    elif case == "clock":
        wire.fake.data["/api/v3/time"]["serverTime"] -= 6000
    elif case == "permissions":
        wire.fake.data["/sapi/v1/account/apiRestrictions"]["enableWithdrawals"] = True
    elif case == "identity":
        wire.order["clientOrderId"] = "wrong"
    elif case == "missing_history":
        wire.trades = []
    elif case == "duplicate":
        wire.trades.append(wire.trades[0])
    elif case == "future_trade":
        wire.trades[0]["time"] += 1000
    elif case == "bad_qty":
        wire.trades[0]["qty"] = "0"
    elif case == "order_changed":
        wire.changed = {**wire.order, "status": "CANCELLED"}
    else:
        wire.order["cummulativeQuoteQty"] = "-1"
    with pytest.raises(NativeError):
        adapter(value, wire).query(client_id(value), value.symbol)
    assert all(x.get_method() == "GET" for x in wire.calls)


@pytest.mark.parametrize("flag", sorted(WRITE_FLAGS))
def test_native_read_keys_cannot_have_write_permissions(
    flag: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pocket_alpha.spot_execution.binance.time.sleep", lambda _: None)
    value = request()
    wire = Wire(value)
    wire.fake.data["/sapi/v1/account/apiRestrictions"][flag] = True
    with pytest.raises(NativeError):
        adapter(value, wire).qualify()
    assert not any(urlsplit(x.full_url).path == "/api/v3/account" for x in wire.calls)


@pytest.mark.parametrize(
    "body",
    [b"invalid", b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * 2_000_001],
    ids=["bad", "duplicate", "nan", "large"],
)
def test_wire_errors_sanitized(body: bytes) -> None:
    value = request()
    wire = Wire(value)
    wire.body = body
    with pytest.raises(NativeError, match="NATIVE_READ_FAILED"):
        adapter(value, wire).qualify()


def test_wrong_routes_keys_and_deadline() -> None:
    value = request()
    wire = Wire(value)
    broker = adapter(value, wire)
    with pytest.raises(NativeError):
        broker.signed_request("POST", "/sapi/v1/capital/withdraw/apply", {})
    with pytest.raises(NativeError):
        broker.signed_request("GET", "/api/v3/order", {})
    with pytest.raises(NativeError):
        broker.query("wrong", value.symbol)
    with pytest.raises(NativeError):
        broker.plan("wrong", value)
    broker.deadline_started = value.proposal.at - timedelta(seconds=31)
    with pytest.raises(NativeError, match="DEADLINE"):
        broker._request("GET", "/api/v3/time", {})
    assert not wire.calls


def test_default_executor_uses_native_but_never_sends(tmp_path: Path) -> None:
    value = request()
    execution = SpotExecution(
        tmp_path / "private.sqlite", policy(value), clock=FrozenClock(value.proposal.at)
    )
    assert isinstance(execution.broker, BinanceSpotBroker)
    assert "FOUNDATION_LIVE_DISABLED" in execution.submit(value)["reasons"]
    execution.journal.close()


def test_qualification_cli_refuses_overwrite_and_no_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "result.json"
    output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["qualify", "--policy", "missing", "--output", str(output)])
    assert main() == 2
    assert output.read_text(encoding="utf-8") == "preserve"
    output.unlink()
    assert main() == 2
    assert SECRET not in capsys.readouterr().out


def test_trading_key_scope_inspection_is_not_execution_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pocket_alpha.spot_execution.binance.time.sleep", lambda _: None)
    value = request()
    wire = Wire(value)
    wire.fake.data["/sapi/v1/account/apiRestrictions"]["enableSpotAndMarginTrading"] = True
    broker = adapter(value, wire)
    inspected = broker.qualify(writing=True)
    assert inspected["contract_validated"] and not inspected["execution_authorized"]
    with pytest.raises(NativeError):
        broker.submit(client_id(value), value)
    wire.fake.data["/sapi/v1/account/apiRestrictions"]["enableInternalTransfer"] = True
    with pytest.raises(NativeError):
        broker.qualify(writing=True)


def test_native_secret_environment_redaction_and_transport_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PA_BINANCE_SPOT_API_KEY", KEY)
    monkeypatch.setenv("PA_BINANCE_SPOT_API_SECRET", SECRET)
    monkeypatch.setenv("PA_BINANCE_SPOT_EXPECTED_UID", "42")
    credentials = SpotCredentials()
    assert credentials.model_dump() == {} and SECRET not in repr(credentials)
    value = request()
    assert adapter(value, Wire(value)).origin == "SYNTHETIC"
    with pytest.raises(NativeError, match="ENDPOINT_NOT_ALLOWED"):
        NativeTransport().send(Request("https://evil.invalid/api/v3/time"), 1, 100)


def test_qualification_cli_receipt_contains_no_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = request()
    config = tmp_path / "policy.json"
    config.write_text(policy(value).model_dump_json(), encoding="utf-8")
    output = tmp_path / "qualified.json"
    monkeypatch.setattr("sys.argv", ["qualify", "--policy", str(config), "--output", str(output)])
    monkeypatch.setattr(
        "pocket_alpha.spot_execution.qualify.BinanceSpotBroker.qualify",
        lambda *args: {
            "acquisition": "NATIVE",
            "read_only_qualified": True,
            "execution_authorized": False,
            "live_trading_enabled": False,
        },
    )
    assert main() == 0
    body = output.read_text(encoding="utf-8")
    assert SECRET not in body and KEY not in body
    assert not json.loads(body)["result"]["execution_authorized"]
