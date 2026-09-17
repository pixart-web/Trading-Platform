import hashlib
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Protocol
from xml.etree import ElementTree

from pydantic import HttpUrl

from pocket_alpha.common.clock import utc
from pocket_alpha.common.public_http import PublicClient, PublicDataError
from pocket_alpha.contextual.models import ContextKind, ContextSample


class ContextProviderError(Exception):
    pass


@dataclass(frozen=True)
class ContextPage:
    records: tuple[ContextSample, ...]
    next_cursor: str | None = None


class ContextProvider(Protocol):
    @property
    def source(self) -> str: ...

    def observations(self, external_entity_id: str, cursor: str | None = None) -> ContextPage: ...


class FederalReserveNewsProvider:
    """Official RSS title/link/date metadata only; not article text or inferred sentiment."""

    source = "federal-reserve-rss"

    def __init__(self, client: PublicClient | None = None) -> None:
        self.client = client or PublicClient()

    def observations(self, external_entity_id: str, cursor: str | None = None) -> ContextPage:
        if external_entity_id != "press-releases" or cursor is not None:
            raise ValueError("Federal Reserve RSS requires the explicit press-releases mapping")
        try:
            body, _ = self.client.get("https://www.federalreserve.gov/feeds/press_all.xml")
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise ContextProviderError("RSS DTD/entities are forbidden")
            root = ElementTree.fromstring(body)
            if root.tag != "rss" or root.find("channel") is None:
                raise ContextProviderError("official RSS document shape invalid")
            items = root.findall("./channel/item")
            if len(items) > 1000:
                raise ContextProviderError("RSS item budget exceeded")
            records = []
            for item in items:
                title, link, published = (
                    item.findtext("title"),
                    item.findtext("link"),
                    item.findtext("pubDate"),
                )
                if not title or not link or not published:
                    raise ContextProviderError("RSS metadata incomplete")
                if HttpUrl(link.strip()).host not in {
                    "www.federalreserve.gov",
                    "federalreserve.gov",
                }:
                    raise ContextProviderError("official news link outside Federal Reserve origin")
                timestamp = utc(parsedate_to_datetime(published))
                event_key = hashlib.sha256((item.findtext("guid") or link).encode()).hexdigest()
                records.append(
                    ContextSample(
                        external_entity_id=external_entity_id,
                        source_record_id=event_key,
                        event_key=event_key,
                        kind=ContextKind.NEWS,
                        event_at=timestamp,
                        published_at=timestamp,
                        title=title.strip(),
                        url=HttpUrl(link.strip()),
                    )
                )
            return ContextPage(tuple(sorted(records, key=lambda r: (r.published_at, r.event_key))))
        except (PublicDataError, ElementTree.ParseError, ValueError, TypeError) as error:
            raise ContextProviderError("Federal Reserve news unavailable or invalid") from error
