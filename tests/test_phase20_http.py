from datetime import timedelta
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest

from pocket_alpha.common import public_http
from pocket_alpha.common.public_http import PublicClient, PublicDataError, Response, UrllibTransport
from tests.market_fixtures import CLOCK
from tests.test_phase20_public_data import Transport


def test_native_get_is_bounded_and_checks_final_https_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.geturl.return_value = "https://example.org/data"
    response.headers = {"Content-Type": "application/json"}
    response.read.return_value = b"data"
    request = MagicMock(return_value=response)
    monkeypatch.setattr(public_http, "urlopen", request)
    result = UrllibTransport().get("https://example.org/data", 3, 100)
    assert result == Response(200, b"data", {"content-type": "application/json"})
    response.read.assert_called_once_with(101)
    assert request.call_args.kwargs["timeout"] == 3
    assert request.call_args.args[0].get_method() == "GET"
    for final in ("https://other.example/data", "http://example.org/data"):
        response.geturl.return_value = final
        with pytest.raises(PublicDataError, match="origin"):
            UrllibTransport().get("https://example.org/data", 3, 100)
    monkeypatch.setattr(public_http, "urlopen", MagicMock(side_effect=URLError("sensitive detail")))
    with pytest.raises(PublicDataError, match="transport failed"):
        UrllibTransport().get("https://example.org/data", 3, 100)


def test_http_error_response_is_closed_and_retry_after_date_respected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = BytesIO(b"rate-limited")
    headers = Message()
    headers["Retry-After"] = "1"
    error = HTTPError("https://example.org/data", 429, "limited", headers, body)
    monkeypatch.setattr(public_http, "urlopen", MagicMock(side_effect=error))
    response = UrllibTransport().get("https://example.org/data", 3, 100)
    assert response.status == 429 and response.headers["retry-after"] == "1"
    assert body.closed
    waits: list[float] = []
    retry = format_datetime(CLOCK.now() + timedelta(seconds=2))
    client = PublicClient(
        transport=Transport(Response(429, b"", {"retry-after": retry}), Response(200, b"ok", {})),
        clock=CLOCK,
        sleep=waits.append,
        monotonic=lambda: 0,
    )
    assert client.get("https://example.org/data")[0] == b"ok"
    assert waits[0] == 2
    malformed = PublicClient(
        transport=Transport(
            Response(429, b"", {"retry-after": "not-a-date"}), Response(200, b"ok", {})
        ),
        clock=CLOCK,
        sleep=waits.append,
        monotonic=lambda: 0,
    )
    assert malformed.get("https://example.org/data")[0] == b"ok"


def test_transport_failures_never_fallback_and_configuration_bounds() -> None:
    transport = MagicMock()
    transport.get.side_effect = PublicDataError("public source transport failed")
    client = PublicClient(transport=transport, sleep=lambda _: None, monotonic=lambda: 0)
    with pytest.raises(PublicDataError):
        client.get("https://example.org/data")
    assert transport.get.call_count == 3
    with pytest.raises(ValueError):
        PublicClient(attempts=0)
    with pytest.raises(ValueError):
        PublicClient(timeout=31)
