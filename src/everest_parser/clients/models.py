"""Минимальные модели transport layer и browser bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BrowserCookie:
    """Cookie, полученная из браузерной bootstrap-сессии."""

    name: str
    value: str
    domain: str | None
    path: str


@dataclass(slots=True)
class BrowserSessionSnapshot:
    """Снимок браузерной сессии для построения HTTP-клиента."""

    site_name: str
    user_agent: str
    cookies: list[BrowserCookie]
    proxy_url: str | None = None


@dataclass(slots=True)
class TransportRequest:
    """Описание HTTP-запроса для transport layer."""

    method: str
    url: str
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    json_body: Any = None
    data: dict[str, Any] | str | bytes | None = None
    timeout_seconds: float | None = None
