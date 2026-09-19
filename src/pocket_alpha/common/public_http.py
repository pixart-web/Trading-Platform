"""Bounded unauthenticated GETs; no private endpoints or raw response logging."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pocket_alpha.common.clock import Clock, SystemClock, utc


class PublicDataError(Exception):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: Mapping[str, str]


class Transport(Protocol):
    def get(self, url: str, timeout: float, maximum_bytes: int) -> Response: ...


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


class UrllibTransport:
    def get(self, url: str, timeout: float, maximum_bytes: int) -> Response:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise PublicDataError("public source origin is invalid")
        try:
            with build_opener(RejectRedirects).open(
                Request(
                    url,
                    headers={
                        "User-Agent": "PocketAlpha/0.1 read-only research",
                        "Accept": "application/json, application/xml",
                    },
                ),
                timeout=timeout,
            ) as response:
                if (urlsplit(response.geturl()).scheme, urlsplit(response.geturl()).netloc) != (
                    urlsplit(url).scheme,
                    urlsplit(url).netloc,
                ):
                    raise PublicDataError("public source redirected outside its origin")
                return Response(
                    response.status,
                    response.read(maximum_bytes + 1),
                    {k.lower(): v for k, v in response.headers.items()},
                )
        except HTTPError as error:
            with error:
                return Response(
                    error.code,
                    error.read(maximum_bytes + 1),
                    {k.lower(): v for k, v in error.headers.items()},
                )
        except (URLError, TimeoutError, OSError) as error:
            raise PublicDataError("public source transport failed") from error


class PublicClient:
    def __init__(
        self,
        *,
        transport: Transport | None = None,
        clock: Clock | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        attempts: int = 3,
        timeout: float = 10,
        maximum_bytes: int = 2_000_000,
    ) -> None:
        if not 1 <= attempts <= 5 or not 1 <= timeout <= 30 or not 1 <= maximum_bytes <= 5_000_000:
            raise ValueError("public HTTP bounds invalid")
        self.transport = transport or UrllibTransport()
        self.clock = clock or SystemClock()
        self.sleep, self.monotonic = sleep, monotonic
        self.attempts, self.timeout, self.maximum_bytes = attempts, timeout, maximum_bytes
        self.last_request: float | None = None

    def get(self, url: str) -> tuple[bytes, datetime]:
        if urlsplit(url).scheme != "https":
            raise ValueError("public sources require HTTPS")
        for attempt in range(self.attempts):
            if self.last_request is not None:
                self.sleep(max(0.0, 0.5 - (self.monotonic() - self.last_request)))
            self.last_request = self.monotonic()
            try:
                response = self.transport.get(url, self.timeout, self.maximum_bytes)
            except PublicDataError:
                if attempt + 1 == self.attempts:
                    raise
                self.sleep(min(0.5 * 2**attempt, 5))
                continue
            received_at = utc(self.clock.now())
            if len(response.body) > self.maximum_bytes:
                raise PublicDataError("public source response exceeds byte budget")
            if response.status == 200:
                return response.body, received_at
            if response.status not in {429, 500, 502, 503, 504}:
                raise PublicDataError(f"public request rejected: status {response.status}")
            if attempt + 1 < self.attempts:
                delay = 0.5 * 2**attempt
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = (
                                utc(parsedate_to_datetime(retry_after)) - received_at
                            ).total_seconds()
                        except (ValueError, TypeError):
                            pass
                if not 0 <= delay <= 5:
                    raise PublicDataError("provider retry embargo exceeds bounded wait")
                self.sleep(delay)
        raise PublicDataError("public request exhausted bounded retries")
