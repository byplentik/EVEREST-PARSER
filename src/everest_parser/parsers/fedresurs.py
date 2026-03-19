"""Парсер `fedresurs.ru` поверх подтвержденных HTTP-endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from everest_parser.clients.models import TransportRequest
from everest_parser.clients.transports import FedresursTransport


@dataclass(slots=True)
class FedresursParseResult:
    """Нормализованный результат парсинга по одному ИНН."""

    inn: str
    case_number: str
    last_publication_date: datetime | None
    raw_payload: dict[str, object]


class FedresursParser:
    """Простой HTTP-парсер `fedresurs.ru` без browser bootstrap."""

    def __init__(self, transport: FedresursTransport | None = None) -> None:
        self.transport = transport or FedresursTransport()

    def close(self) -> None:
        """Закрыть связанные ресурсы transport layer."""

        self.transport.close()

    def parse_inn(self, inn: str) -> FedresursParseResult | None:
        """Получить данные о банкротстве по одному ИНН."""

        search_payload = self._search_person(inn)
        match = select_search_match(search_payload, inn)
        if match is None:
            return None

        bankruptcy_payload = self._fetch_bankruptcy(match["guid"])
        case_number, last_publication_date = select_bankruptcy_result(bankruptcy_payload)
        if not case_number:
            return None

        return FedresursParseResult(
            inn=match["inn"],
            case_number=case_number,
            last_publication_date=last_publication_date,
            raw_payload={
                "guid": match["guid"],
                "search_response_json": search_payload,
                "bankruptcy_response_json": bankruptcy_payload,
            },
        )

    def _search_person(self, inn: str) -> dict[str, Any]:
        """Выполнить `persons/fast` по ИНН."""

        response = self.transport.execute(
            TransportRequest(
                method="GET",
                url="https://fedresurs.ru/backend/persons/fast",
                params={"searchString": inn},
            )
        )
        return response.json()

    def _fetch_bankruptcy(self, guid: str) -> dict[str, Any]:
        """Загрузить endpoint `persons/{guid}/bankruptcy`."""

        response = self.transport.execute(
            TransportRequest(
                method="GET",
                url=f"https://fedresurs.ru/backend/persons/{guid}/bankruptcy",
            )
        )
        return response.json()


def select_search_match(payload: dict[str, Any], inn: str) -> dict[str, str] | None:
    """Выбрать подходящий результат `persons/fast`."""

    normalized_inn = normalize_inn(inn)
    page_data = payload.get("pageData") or []
    fallback: dict[str, str] | None = None

    for item in page_data:
        guid = str(item.get("guid") or "").strip()
        item_inn = normalize_inn(item.get("inn"))
        if not guid or not item_inn:
            continue

        candidate = {"guid": guid, "inn": item_inn}
        if fallback is None:
            fallback = candidate

        if item_inn == normalized_inn:
            return candidate

    return fallback


def select_bankruptcy_result(payload: dict[str, Any]) -> tuple[str | None, datetime | None]:
    """Выбрать номер дела и максимальную дату публикации из ответа bankruptcy."""

    legal_cases = payload.get("legalCases") or []
    if not legal_cases and payload.get("number"):
        legal_cases = [payload]

    fallback_case_number: str | None = None
    best_case_number: str | None = None
    best_publication_date: datetime | None = None

    for legal_case in legal_cases:
        case_number = str(legal_case.get("number") or "").strip()
        if case_number and fallback_case_number is None:
            fallback_case_number = case_number

        for publication in legal_case.get("lastPublications") or []:
            publication_date = parse_publication_datetime(publication.get("datePublish"))
            if publication_date is None or not case_number:
                continue

            if best_publication_date is None or publication_date > best_publication_date:
                best_case_number = case_number
                best_publication_date = publication_date

    if best_case_number is not None:
        return best_case_number, best_publication_date

    return fallback_case_number, None


def parse_publication_datetime(value: object) -> datetime | None:
    """Преобразовать строку даты публикации `fedresurs` в `datetime`."""

    if not isinstance(value, str) or not value.strip():
        return None

    normalized_value = value.strip().replace("Z", "+00:00")
    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value


def normalize_inn(value: object) -> str:
    """Нормализовать ИНН до строки из цифр."""

    return "".join(symbol for symbol in str(value or "") if symbol.isdigit())
