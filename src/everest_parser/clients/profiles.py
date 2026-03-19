"""Профили сайтов и правила сборки browser-like заголовков."""

from __future__ import annotations

from dataclasses import dataclass
import re

import httpx


CHROME_VERSION_RE = re.compile(r"Chrome/(?P<major>\d+)")
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.7680.153 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class SiteProfile:
    """Профиль сайта для transport layer."""

    site_name: str
    base_headers: dict[str, str]
    invalid_status_codes: frozenset[int]
    blocked_body_markers: tuple[str, ...]
    blocked_server_markers: tuple[str, ...]


FEDRESURS_PROFILE = SiteProfile(
    site_name="fedresurs",
    base_headers={
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://fedresurs.ru/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    },
    invalid_status_codes=frozenset({401, 403}),
    blocked_body_markers=("qrator", "qrator_jsid", "403 forbidden"),
    blocked_server_markers=(),
)

KAD_PROFILE = SiteProfile(
    site_name="kad",
    base_headers={
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": "https://kad.arbitr.ru",
        "Referer": "https://kad.arbitr.ru/Kad",
    },
    invalid_status_codes=frozenset({401, 403, 451}),
    blocked_body_markers=(
        "ddos-guard",
        "access denied",
        "pravocaptcha",
        "recaptchatoken",
        "подтверждение действия",
    ),
    blocked_server_markers=(),
)


def detect_platform_from_user_agent(user_agent: str) -> str:
    """Определить платформу для client hints по user-agent."""

    lower_user_agent = user_agent.lower()
    if "windows" in lower_user_agent:
        return "Windows"
    if "linux" in lower_user_agent:
        return "Linux"
    if "mac os x" in lower_user_agent or "macintosh" in lower_user_agent:
        return "macOS"
    return "Unknown"


def extract_chrome_major(user_agent: str) -> str | None:
    """Извлечь major-версию Chrome из user-agent."""

    match = CHROME_VERSION_RE.search(user_agent)
    if match is None:
        return None

    return match.group("major")


def build_client_hints_headers(user_agent: str) -> dict[str, str]:
    """Собрать упрощенный набор Chromium client hints по user-agent."""

    major = extract_chrome_major(user_agent)
    if major is None:
        return {}

    platform = detect_platform_from_user_agent(user_agent)

    return {
        "Sec-CH-UA": (
            f'"Not:A-Brand";v="99", "Google Chrome";v="{major}", "Chromium";v="{major}"'
        ),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": f'"{platform}"',
    }


def build_site_headers(
    profile: SiteProfile,
    user_agent: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Собрать итоговые заголовки для сайта поверх user-agent и extra headers."""

    headers = {
        **profile.base_headers,
        **build_client_hints_headers(user_agent),
        "User-Agent": user_agent,
    }

    if extra_headers:
        headers.update(extra_headers)

    return headers


def response_looks_blocked(profile: SiteProfile, response: httpx.Response) -> bool:
    """Проверить, что ответ похож на блокировку или антибот-страницу."""

    if response.status_code in profile.invalid_status_codes:
        return True

    server_header = response.headers.get("server", "").lower()
    if any(marker in server_header for marker in profile.blocked_server_markers):
        return True

    body_preview = response.text[:4000].lower()
    return any(marker in body_preview for marker in profile.blocked_body_markers)
