"""Минимальный lifecycle браузерной и HTTP-сессии для `kad.arbitr.ru`."""

from __future__ import annotations

import httpx

from everest_parser.browser.kad_bootstrap import KadBootstrapper
from everest_parser.clients.models import BrowserCookie
from everest_parser.clients.models import BrowserSessionSnapshot
from everest_parser.clients.profiles import KAD_PROFILE
from everest_parser.clients.profiles import build_site_headers
from everest_parser.config import Settings
from everest_parser.config import get_settings
from everest_parser.utils import print_project_log


class KadSessionManager:
    """Менеджер одной HTTP-сессии `kad` на текущий запуск."""

    def __init__(
        self,
        settings: Settings | None = None,
        bootstrapper: KadBootstrapper | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.bootstrapper = bootstrapper or KadBootstrapper(self.settings)
        self._snapshot: BrowserSessionSnapshot | None = None
        self._client: httpx.Client | None = None

    @property
    def user_agent(self) -> str:
        """Вернуть текущий user-agent bootstrap-сессии."""

        if self._snapshot is None:
            self.get_client()
        assert self._snapshot is not None
        return self._snapshot.user_agent

    def get_client(self) -> httpx.Client:
        """Вернуть активный HTTP-клиент `kad`, при необходимости создав его."""

        if self._client is None:
            log_kad_session_event("Активной HTTP-сессии kad нет. Запускаем browser bootstrap.")
            self._snapshot = self.bootstrapper.bootstrap()
            self._client = self._build_client(self._snapshot)

        return self._client

    def refresh(self, reason: str) -> httpx.Client:
        """Пересобрать browser snapshot и HTTP-сессию `kad`."""

        log_kad_session_event(f"Обновляем kad-сессию. Причина: {reason}.")
        self.close()
        return self.get_client()

    def close(self) -> None:
        """Закрыть текущую HTTP-сессию `kad`."""

        if self._client is not None:
            self._client.close()
            self._client = None
            self._snapshot = None

    def _build_client(self, snapshot: BrowserSessionSnapshot) -> httpx.Client:
        """Собрать `httpx.Client` поверх browser snapshot."""

        client = httpx.Client(
            headers=build_site_headers(KAD_PROFILE, snapshot.user_agent),
            timeout=self.settings.http_timeout_seconds,
            verify=self.settings.http_verify_ssl,
            proxy=snapshot.proxy_url,
            follow_redirects=True,
        )

        for cookie in snapshot.cookies:
            self._set_cookie(client, cookie)

        client.cookies.set("SiteVersion", "Full", domain=".arbitr.ru", path="/")
        return client

    def _set_cookie(self, client: httpx.Client, cookie: BrowserCookie) -> None:
        """Перенести одну browser-cookie в jar HTTP-клиента."""

        client.cookies.set(
            cookie.name,
            cookie.value,
            domain=cookie.domain or "",
            path=cookie.path or "/",
        )


def log_kad_session_event(message: str) -> None:
    """Вывести служебный лог lifecycle HTTP-сессии `kad`."""

    print_project_log("kad", message)
