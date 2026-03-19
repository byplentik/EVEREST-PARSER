"""browser bootstrap для `kad.arbitr.ru` через undetected-chromedriver."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys
import tempfile
from time import sleep
from typing import Any

from selenium.common.exceptions import JavascriptException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from everest_parser.clients.errors import TransportConfigError
from everest_parser.clients.models import BrowserCookie
from everest_parser.clients.models import BrowserSessionSnapshot
from everest_parser.config import Settings
from everest_parser.config import get_settings
from everest_parser.utils import print_project_log


KAD_BOOTSTRAP_URL = "https://kad.arbitr.ru/Kad"
KAD_PROBE_CASE_NUMBER = "А32-28873/2024"
BROWSER_BOOTSTRAP_ATTEMPTS = 3
PAGE_LOAD_TIMEOUT_SECONDS = 60
BOOTSTRAP_WAIT_SECONDS = 20
POST_LOAD_WAIT_SECONDS = 5
BROWSER_WINDOW_WIDTH = 1920
BROWSER_WINDOW_HEIGHT = 1080


class KadBootstrapError(Exception):
    """Ошибка bootstrap-сессии `kad.arbitr.ru`."""


def resolve_kad_proxy_url(settings: Settings) -> str | None:
    """Определить proxy для `kad`."""

    http_proxy = settings.http_proxy_url
    browser_proxy = settings.browser_proxy_url

    if http_proxy and browser_proxy and http_proxy != browser_proxy:
        raise TransportConfigError(
            "Для kad proxy браузера и HTTP должны совпадать."
        )

    return browser_proxy or http_proxy


class KadBootstrapper:
    """Сборщик browser snapshot для `kad.arbitr.ru`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def bootstrap(self) -> BrowserSessionSnapshot:
        """Поднять браузер, прогреть сессию и вернуть snapshot cookie."""

        proxy_url = resolve_kad_proxy_url(self.settings)
        last_error: KadBootstrapError | None = None

        for attempt in range(1, BROWSER_BOOTSTRAP_ATTEMPTS + 1):
            log_kad_bootstrap_event(
                f"Bootstrap браузера kad: попытка {attempt}/{BROWSER_BOOTSTRAP_ATTEMPTS}."
            )
            profile_dir = Path(tempfile.mkdtemp(prefix="kad-profile-"))
            driver: Any | None = None

            try:
                driver = self._build_driver(proxy_url, profile_dir)
                log_kad_bootstrap_event("Браузер kad поднят, открываем стартовую страницу.")
                driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
                driver.get(KAD_BOOTSTRAP_URL)
                self._wait_document_ready(driver)
                sleep(POST_LOAD_WAIT_SECONDS)
                self._wait_session_cookies(driver)
                log_kad_bootstrap_event("Базовые cookie kad получены, подтверждаем рабочую сессию.")
                self._warm_up_search(driver)

                snapshot = BrowserSessionSnapshot(
                    site_name="kad",
                    user_agent=self._get_user_agent(driver),
                    cookies=self._get_cookies(driver),
                    proxy_url=proxy_url,
                )
                if not snapshot.cookies:
                    raise KadBootstrapError("Не удалось получить cookie для kad bootstrap-сессии.")

                log_kad_bootstrap_event(
                    f"Bootstrap kad завершен успешно. Собрано cookie: {len(snapshot.cookies)}."
                )
                return snapshot
            except WebDriverException as error:
                last_error = KadBootstrapError(str(error))
                log_kad_bootstrap_event(f"Bootstrap kad завершился ошибкой webdriver: {error}")
            except KadBootstrapError as error:
                last_error = error
                log_kad_bootstrap_event(f"Bootstrap kad завершился ошибкой: {error}")
            finally:
                if driver is not None:
                    driver.quit()
                shutil.rmtree(profile_dir, ignore_errors=True)

            sleep(2)

        if last_error is None:
            raise KadBootstrapError("Не удалось поднять bootstrap-сессию kad.")
        raise last_error

    def _build_driver(self, proxy_url: str | None, profile_dir: Path) -> Any:
        """Создать экземпляр `undetected-chromedriver`."""

        uc = self._import_undetected_chromedriver()
        options = uc.ChromeOptions()
        options.add_argument(f"--window-size={BROWSER_WINDOW_WIDTH},{BROWSER_WINDOW_HEIGHT}")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
        options.add_argument("--profile-directory=Default")

        if proxy_url:
            options.add_argument(f"--proxy-server={proxy_url}")

        return uc.Chrome(
            options=options,
            headless=False,
            user_data_dir=str(profile_dir.resolve()),
            use_subprocess=False,
        )

    def _wait_document_ready(self, driver: Any) -> None:
        """Дождаться полной загрузки страницы."""

        deadline = datetime.now().timestamp() + PAGE_LOAD_TIMEOUT_SECONDS
        while datetime.now().timestamp() < deadline:
            try:
                if driver.execute_script("return document.readyState;") == "complete":
                    return
            except JavascriptException as error:
                raise KadBootstrapError("Не удалось получить `document.readyState` для kad.") from error
            sleep(0.5)

        raise KadBootstrapError("Истек таймаут ожидания полной загрузки страницы kad.")

    def _wait_session_cookies(self, driver: Any) -> None:
        """Подождать, пока `kad` выдаст базовый набор cookie."""

        deadline = datetime.now().timestamp() + BOOTSTRAP_WAIT_SECONDS
        while datetime.now().timestamp() < deadline:
            cookie_names = {cookie["name"] for cookie in driver.get_cookies()}
            has_ddg_cookie = any(cookie_name.startswith("__ddg") for cookie_name in cookie_names)
            if {"CUID", "ASP.NET_SessionId"} <= cookie_names and has_ddg_cookie:
                return
            sleep(1)

        raise KadBootstrapError("Истек таймаут ожидания bootstrap-cookie для kad.")

    def _warm_up_search(self, driver: Any) -> None:
        """Инициировать штатный UI-поиск, чтобы `kad` выдал рабочую сессию."""

        try:
            input_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#sug-cases input"))
            )
        except TimeoutException as error:
            raise KadBootstrapError("Не удалось найти поле `Номер дела` на странице kad.") from error

        for _ in range(2):
            self._clear_resource_timings(driver)
            input_element.click()
            input_element.clear()
            input_element.send_keys(KAD_PROBE_CASE_NUMBER)

            try:
                driver.execute_script(
                    """
const input = arguments[0];
input.dispatchEvent(new Event('input', { bubbles: true }));
input.dispatchEvent(new Event('change', { bubbles: true }));
if (window.stateOfButton) {
  window.stateOfButton();
}
""",
                    input_element,
                )
            except WebDriverException:
                pass

            self._click_search_button(driver)
            state = self._wait_search_state(driver)

            if state["blocked"]:
                raise KadBootstrapError("UI-bootstrap `kad` уперся в блокировку при пробном поиске.")
            if state["hasSearchRequest"] or state["hasCaseLink"]:
                return

        raise KadBootstrapError(
            "Не удалось инициировать UI-поиск `kad`: кнопка `Найти` не отправила `SearchInstances`."
        )

    def _click_search_button(self, driver: Any) -> None:
        """Нажать кнопку `Найти`."""

        try:
            button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#b-form-submit"))
            )
            button.click()
        except WebDriverException as error:
            raise KadBootstrapError("Не удалось нажать кнопку `Найти` на странице kad.") from error

    def _wait_search_state(self, driver: Any) -> dict[str, bool]:
        """Дождаться первого заметного результата UI-поиска."""

        deadline = datetime.now().timestamp() + 10
        last_state = self._collect_search_state(driver)

        while datetime.now().timestamp() < deadline:
            last_state = self._collect_search_state(driver)
            if last_state["blocked"] or last_state["hasSearchRequest"] or last_state["hasCaseLink"]:
                return last_state
            sleep(0.5)

        return last_state

    def _collect_search_state(self, driver: Any) -> dict[str, bool]:
        """Собрать краткое состояние UI после нажатия `Найти`."""

        try:
            payload = driver.execute_script(
                """
const text = document.body ? document.body.innerText : '';
return {
  hasCaseLink: Boolean(document.querySelector('a.num_case[href*="/Card/"]')),
  hasSearchRequest: performance.getEntriesByType('resource')
    .some((entry) => entry.name.includes('/Kad/SearchInstances')),
  blocked: text.includes('Доступ к сервису ограничен') || text.includes('Доступ заблокирован'),
};
"""
            )
        except JavascriptException as error:
            raise KadBootstrapError("Не удалось собрать состояние UI-поиска `kad`.") from error

        if not isinstance(payload, dict):
            return {"hasCaseLink": False, "hasSearchRequest": False, "blocked": False}
        return {
            "hasCaseLink": bool(payload.get("hasCaseLink")),
            "hasSearchRequest": bool(payload.get("hasSearchRequest")),
            "blocked": bool(payload.get("blocked")),
        }

    def _clear_resource_timings(self, driver: Any) -> None:
        """Очистить browser resource timings перед очередной попыткой поиска."""

        try:
            driver.execute_script(
                """
if (window.performance && window.performance.clearResourceTimings) {
  window.performance.clearResourceTimings();
}
"""
            )
        except WebDriverException:
            return

    def _get_user_agent(self, driver: Any) -> str:
        """Извлечь фактический user-agent браузера."""

        try:
            user_agent = driver.execute_script("return navigator.userAgent;")
        except JavascriptException as error:
            raise KadBootstrapError("Не удалось получить user-agent из браузера.") from error

        if not isinstance(user_agent, str) or not user_agent.strip():
            raise KadBootstrapError("Браузер вернул пустой user-agent.")

        return user_agent.strip().replace("HeadlessChrome/", "Chrome/")

    def _get_cookies(self, driver: Any) -> list[BrowserCookie]:
        """Собрать browser-cookie в нормализованный список."""

        return [
            BrowserCookie(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )
            for cookie in driver.get_cookies()
        ]

    def _import_undetected_chromedriver(self) -> Any:
        """Ленивая загрузка `undetected_chromedriver`."""

        try:
            import undetected_chromedriver as uc
        except ModuleNotFoundError as error:
            if error.name == "distutils":
                raise KadBootstrapError(
                    "undetected-chromedriver 3.5.5 требует distutils. Используй Docker или Python 3.11."
                ) from error
            raise KadBootstrapError(str(error)) from error

        if sys.version_info >= (3, 12):
            raise KadBootstrapError(
                "Для работы undetected-chromedriver 3.5.5 нужен Python 3.11."
            )

        return uc


def log_kad_bootstrap_event(message: str) -> None:
    """Вывести служебный лог bootstrap-сессии `kad`."""

    print_project_log("kad", message)
