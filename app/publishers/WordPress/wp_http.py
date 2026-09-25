"""HTTP-транспорт WordPress-публишера: куки, bot-protection, ретраи.

Отделено от ``wordpress``: тот держал сразу транспорт, form-логин, Podlove
REST и сборку поста — 489 строк. Миксин, а не отдельный объект, чтобы
перенос остался механическим: методы работают с теми же ``self._session`` /
``self._cookie_path``, что и раньше.
"""

import json
import os
import re
from time import sleep

import requests
from loguru import logger
from requests import Response

HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
HTTP_BACKOFF_BASE = 2.0


class WordPressHttpMixin:
    """Требует от класса-хозяина ``_session`` и ``_cookie_path``."""

    def _dump_cookies(self) -> bool:
        """Сохраняет куки сессии в JSON.

        Раньше тут был ``pickle.dump``: загрузка такого файла исполняет
        произвольный код, а формат нечитаем глазами. Пишем name/value/domain/path
        явно — domain нужен для bot-protection куки, которая ставится на
        конкретный домен.
        """
        if not self._cookie_path:
            raise ValueError("Cookie path cannot be empty")
        try:
            jar = [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path} for c in self._session.cookies
            ]
            with open(self._cookie_path, "w", encoding="utf-8") as f:
                json.dump(jar, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
            return False

    def _load_cookies(self) -> bool:
        if not (os.path.exists(self._cookie_path) and os.path.getsize(self._cookie_path) > 0):
            return False
        try:
            with open(self._cookie_path, encoding="utf-8") as f:
                jar = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Файл от прежней pickle-версии. Читать его не будем — pickle.load
            # исполняет произвольный код. Логинимся заново, _dump_cookies
            # перезапишет файл в JSON.
            logger.warning(f"{self._cookie_path} is not JSON (legacy pickle?); re-authenticating instead")
            return False
        for c in jar:
            self._session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        return True

    @staticmethod
    def _bot_protection_cookie(html: str) -> tuple[str, str, str] | None:
        """Detect a JS-only bot-protection challenge and extract its cookie.

        Some WP sites front every page with a tiny challenge response:
            <html><body><script>
              document.cookie="bpc=<hash>;Domain=<domain>;Path=/";
              document.location.href="<url>";
            </script></body></html>
        A real browser runs the JS — sets the cookie and re-navigates —
        and the second request goes through. `requests` doesn't run JS,
        so without help we keep getting the challenge page back forever.

        Returns (name, value, domain) when the response is one of these
        challenges, None for any normal page.
        """
        m = re.search(
            r'<script[^>]*>\s*document\.cookie\s*=\s*"([^"=]+)=([^";]+);'
            r'\s*Domain\s*=\s*([^";]+);',
            html,
            re.IGNORECASE,
        )
        if not m:
            return None
        return m.group(1), m.group(2), m.group(3)

    def _request(self, session: requests.Session, method: str, url: str, **kwargs) -> Response:
        """`session.request` with one-shot bot-protection cookie handling.

        Defaults `timeout=HTTP_TIMEOUT`. On a bot-protection challenge
        response (see _bot_protection_cookie) sets the demanded cookie
        on `session` and replays the same request exactly once. The
        challenge cookie sticks in the session for subsequent calls.
        """
        kwargs.setdefault("timeout", HTTP_TIMEOUT)
        response = session.request(method, url, **kwargs)
        bpc = self._bot_protection_cookie(response.text)
        if bpc is None:
            return response
        name, value, domain = bpc
        session.cookies.set(name, value, domain=domain, path="/")
        logger.info(f"Bot-protection challenge: set {name}={value[:8]}... domain={domain}; replaying {method} {url}")
        response = session.request(method, url, **kwargs)
        # If still a challenge after retry, give up gracefully — return the
        # response and let the caller's normal logic see the body.
        if self._bot_protection_cookie(response.text) is not None:
            logger.warning(f"Bot-protection challenge re-appeared after cookie set; giving up on {method} {url}")
        return response

    def _get_with_retry(self, url: str) -> Response:
        """GET with timeout and exponential backoff on transport/5xx errors.

        Retries on connection errors, timeouts, and 5xx responses. Returns
        the final Response (which may still be a 4xx) once retries are
        exhausted or a non-5xx is received. Raises RuntimeError if every
        attempt fails at the transport layer.
        """
        last_error: Exception | None = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                r = self._request(self._session, "GET", url)
            except requests.RequestException as e:
                last_error = e
                logger.warning(f"GET {url} failed on attempt {attempt}/{HTTP_RETRIES}: {e!r}")
            else:
                if r.status_code < 500:
                    return r
                last_error = RuntimeError(f"server returned {r.status_code}")
                logger.warning(
                    f"GET {url} returned {r.status_code} on attempt {attempt}/{HTTP_RETRIES}; "
                    f"body[:300]={r.text[:300]!r}"
                )
            if attempt < HTTP_RETRIES:
                sleep(HTTP_BACKOFF_BASE ** (attempt - 1))
        raise RuntimeError(f"GET {url} failed after {HTTP_RETRIES} attempts: {last_error!r}")
