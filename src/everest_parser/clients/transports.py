"""Минимальный HTTP transport для `fedresurs` и `kad`."""

from __future__ import annotations

import time
from typing import Any

import httpx

from everest_parser.clients.errors import BlockedResponseError
from everest_parser.clients.errors import TransportRequestError
from everest_parser.clients.models import TransportRequest
from everest_parser.clients.profiles import DEFAULT_BROWSER_USER_AGENT
from everest_parser.clients.profiles import FEDRESURS_PROFILE
from everest_parser.clients.profiles import KAD_PROFILE
from everest_parser.clients.profiles import SiteProfile
from everest_parser.clients.profiles import build_site_headers
from everest_parser.clients.profiles import response_looks_blocked
from everest_parser.clients.session_manager import KadSessionManager
from everest_parser.config import Settings
from everest_parser.config import get_settings


class BaseTransport:
    """Базовый transport layer с retry-настройками."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def close(self) -> None:
        """Закрыть связанные ресурсы транспорта."""

    def _sleep_before_retry(self, attempt: int) -> None:
        """Подождать перед следующей попыткой сетевого запроса."""

        time.sleep(min(self.settings.request_delay_seconds * attempt, 10))

    def _build_request_kwargs(
        self,
        request: TransportRequest,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Собрать kwargs для `httpx.Client.request`."""

        return {
            "method": request.method.upper(),
            "url": request.url,
            "params": request.params,
            "headers": headers,
            "json": request.json_body,
            "data": request.data,
            "timeout": request.timeout_seconds or self.settings.http_timeout_seconds,
        }

    def _raise_blocked_error(self, profile: SiteProfile, response: httpx.Response) -> None:
        """Поднять структурированную ошибку блокировки по ответу сайта."""

        raise BlockedResponseError(
            f"{profile.site_name}: ответ похож на блокировку. "
            f"status={response.status_code}, url={response.url}"
        )


class FedresursTransport(BaseTransport):
    """Прямой HTTP-транспорт для `fedresurs.ru` без browser bootstrap."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings=settings)
        self._client = httpx.Client(
            headers=build_site_headers(FEDRESURS_PROFILE, DEFAULT_BROWSER_USER_AGENT),
            timeout=self.settings.http_timeout_seconds,
            verify=self.settings.http_verify_ssl,
            proxy=self.settings.http_proxy_url,
            follow_redirects=True,
        )

    def execute(self, request: TransportRequest) -> httpx.Response:
        """Выполнить HTTP-запрос к `fedresurs` с сетевыми retry."""

        last_error: Exception | None = None

        for attempt in range(1, self.settings.max_retries + 1):
            headers = build_site_headers(
                FEDRESURS_PROFILE,
                DEFAULT_BROWSER_USER_AGENT,
                request.headers,
            )

            try:
                response = self._client.request(
                    **self._build_request_kwargs(request=request, headers=headers)
                )
            except httpx.RequestError as error:
                last_error = error
                if attempt >= self.settings.max_retries:
                    raise TransportRequestError(str(error)) from error
                self._sleep_before_retry(attempt)
                continue

            if response_looks_blocked(FEDRESURS_PROFILE, response):
                self._raise_blocked_error(FEDRESURS_PROFILE, response)

            return response

        raise TransportRequestError(str(last_error))

    def close(self) -> None:
        """Закрыть HTTP-клиент `fedresurs`."""

        self._client.close()


class KadTransport(BaseTransport):
    """HTTP-транспорт для `kad` поверх browser bootstrap."""

    def __init__(
        self,
        settings: Settings | None = None,
        session_manager: KadSessionManager | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self.session_manager = session_manager or KadSessionManager(self.settings)

    def execute(self, request: TransportRequest) -> httpx.Response:
        """Выполнить HTTP-запрос к `kad` с refresh browser session при блокировке."""

        last_error: Exception | None = None

        for attempt in range(1, self.settings.max_retries + 1):
            client = self.session_manager.get_client()
            headers = build_site_headers(KAD_PROFILE, self.session_manager.user_agent, request.headers)

            try:
                response = client.request(
                    **self._build_request_kwargs(request=request, headers=headers)
                )
            except httpx.RequestError as error:
                last_error = error
                if attempt >= self.settings.max_retries:
                    raise TransportRequestError(str(error)) from error
                self._sleep_before_retry(attempt)
                continue

            if response_looks_blocked(KAD_PROFILE, response):
                last_error = BlockedResponseError(
                    f"kad: ответ похож на блокировку. status={response.status_code}, url={response.url}"
                )
                if attempt >= self.settings.max_retries:
                    raise last_error
                self.session_manager.refresh("blocked_response")
                self._sleep_before_retry(attempt)
                continue

            return response

        if last_error is None:
            raise TransportRequestError("Не удалось выполнить запрос к kad.")
        raise last_error

    def close(self) -> None:
        """Закрыть lifecycle-сессию `kad`."""

        self.session_manager.close()
