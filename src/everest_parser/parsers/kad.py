"""Парсер `kad.arbitr.ru` поверх подтвержденных HTTP-endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from html import unescape
import re

from everest_parser.clients.models import TransportRequest
from everest_parser.clients.transports import KadTransport


CASE_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<card_url>https://kad\.arbitr\.ru/Card/(?P<uid>[0-9a-f\-]{36}))"[^>]*class="num_case"[^>]*>(?P<label>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
REG_DATE_RE = re.compile(
    r'<span[^>]*class="b-reg-date"[^>]*>(?P<date>\d{2}\.\d{2}\.\d{4})</span>',
    re.IGNORECASE,
)
CASE_RESULT_RE = re.compile(
    r'<h2[^>]*class="b-case-result"[^>]*>(?P<content>.*?)</h2>',
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r'href="(?P<href>[^"]+)"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class KadSearchMatch:
    """Совпадение по делу из `SearchInstances`."""

    case_number: str
    case_uid: str
    card_url: str


@dataclass(slots=True)
class KadParseResult:
    """Нормализованный результат парсинга карточки дела `kad`."""

    case_number: str
    case_uid: str
    card_url: str
    document_date: date | None
    document_name: str
    document_url: str | None
    raw_payload: dict[str, object]


class KadArbitrParser:
    """Парсер `kad.arbitr.ru`, использующий `SearchInstances` и `Card/{uid}`."""

    def __init__(self, transport: KadTransport | None = None) -> None:
        self.transport = transport or KadTransport()

    def close(self) -> None:
        """Закрыть связанные ресурсы transport layer."""

        self.transport.close()

    def parse_case(self, case_number: str) -> KadParseResult | None:
        """Получить карточку дела и извлечь итоговые данные для одной задачи."""

        normalized_case_number = normalize_case_number(case_number)
        search_match, search_html = self._search_case(normalized_case_number)
        if search_match is None:
            return None

        card_html = self._fetch_card_page(search_match.card_url)
        document_date = parse_document_date(card_html)
        document_name, document_url = parse_document_result(card_html)

        return KadParseResult(
            case_number=search_match.case_number,
            case_uid=search_match.case_uid,
            card_url=search_match.card_url,
            document_date=document_date,
            document_name=document_name,
            document_url=document_url,
            raw_payload={
                "case_uid": search_match.case_uid,
                "card_url": search_match.card_url,
                "document_url": document_url,
                "search_response_html": search_html,
                "card_response_html": card_html,
            },
        )

    def _search_case(self, case_number: str) -> tuple[KadSearchMatch | None, str]:
        """Выполнить `SearchInstances` и выбрать подходящее совпадение по номеру дела."""

        response = self.transport.execute(
            TransportRequest(
                method="POST",
                url="https://kad.arbitr.ru/Kad/SearchInstances",
                headers={
                    "Accept": "*/*",
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-Date-Format": "iso",
                    "Cache-Control": "no-cache",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                },
                json_body={
                    "Page": 1,
                    "Count": 25,
                    "Courts": [],
                    "DateFrom": None,
                    "DateTo": None,
                    "Sides": [],
                    "Judges": [],
                    "CaseNumbers": [case_number],
                    "WithVKSInstances": False,
                },
            )
        )
        html_text = response.text
        return parse_search_match(html_text, case_number), html_text

    def _fetch_card_page(self, card_url: str) -> str:
        """Загрузить HTML карточки дела по прямой ссылке."""

        response = self.transport.execute(
            TransportRequest(
                method="GET",
                url=card_url,
            )
        )
        return response.text


def parse_search_match(html_text: str, case_number: str) -> KadSearchMatch | None:
    """Извлечь совпадение по делу из HTML `SearchInstances`."""

    normalized_case_number = normalize_case_number(case_number)
    fallback_match: KadSearchMatch | None = None

    for match in CASE_LINK_RE.finditer(html_text):
        candidate_case_number = normalize_case_number(strip_html(match.group("label")))
        candidate = KadSearchMatch(
            case_number=candidate_case_number,
            case_uid=match.group("uid"),
            card_url=match.group("card_url"),
        )

        if fallback_match is None:
            fallback_match = candidate

        if candidate_case_number == normalized_case_number:
            return candidate

    return fallback_match


def parse_document_date(html_text: str) -> date | None:
    """Извлечь дату последнего документа из карточки дела."""

    match = REG_DATE_RE.search(html_text)
    if match is None:
        return None
    return datetime.strptime(match.group("date"), "%d.%m.%Y").date()


def parse_document_result(html_text: str) -> tuple[str, str | None]:
    """Извлечь название последнего документа и ссылку на PDF из карточки дела."""

    match = CASE_RESULT_RE.search(html_text)
    if match is None:
        raise ValueError("Не удалось найти блок `b-case-result` в карточке дела kad.")

    content = match.group("content")
    href_match = HREF_RE.search(content)
    document_url = href_match.group("href") if href_match is not None else None
    document_name = strip_html(content)

    if not document_name:
        raise ValueError("Не удалось извлечь название документа из карточки дела kad.")

    return document_name, document_url


def strip_html(value: str) -> str:
    """Убрать HTML-теги и нормализовать пробелы."""

    text = TAG_RE.sub(" ", value)
    text = unescape(text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_case_number(value: str) -> str:
    """Нормализовать номер дела для внутреннего сравнения."""

    normalized = unescape(value).replace("\u00a0", " ").upper().strip()
    normalized = normalized.replace("\\", "/")
    normalized = normalized.replace("–", "-")
    normalized = normalized.replace("—", "-")
    normalized = normalized.replace("−", "-")
    normalized = SPACE_RE.sub("", normalized)
    return normalized
