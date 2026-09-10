"""Podlove REST API: метаданные эпизода и главы.

Отдельный от wp-admin путь: форму постов мы скрейпим, а Podlove правим
через REST по Application Password. Выделено из ``wordpress`` вместе с
:mod:`wp_http`.
"""

import json
import re

import requests
from loguru import logger
from requests import Response


class PodloveMixin:
    """Требует ``_rest_session``, ``_app_auth``, ``_wp_url``, ``_user_agent``."""

    def _rest_request(self, method: str, path: str, *, json_body: dict | None = None) -> Response:
        """Authenticated REST API request via Application Password.

        Uses a bare `requests.request` (not the cookie session) on purpose:
        WordPress prefers cookie auth over basic auth when both are present,
        and cookie auth on REST API requires an `X-WP-Nonce` header — without
        it the server returns 401 `rest_forbidden`. Sending only Basic auth
        avoids that ambiguity.
        """
        if self._app_auth is None:
            raise RuntimeError("WP_APP_PASSWORD is not configured; REST API call impossible")
        url = f"{self._wp_url}/wp-json{path}"
        try:
            r = self._request(self._rest_session, method, url, json=json_body, auth=self._app_auth)
        except requests.RequestException as e:
            logger.error(f"REST {method} {path} transport failed: {e!r}")
            raise RuntimeError(f"REST {method} {path} transport failed: {e!r}") from e
        if not r.ok:
            logger.error(f"REST {method} {path} returned HTTP {r.status_code}; body[:500]={r.text[:500]!r}")
            raise RuntimeError(f"REST {method} {path} returned HTTP {r.status_code}")
        return r

    @staticmethod
    def _extract_podlove_vue(html: str) -> dict | None:
        """Parse the `podlove_vue` JS object embedded in the post-new page.

        The page reserves both a WP post_id and a Podlove episode_id and prints
        them as a JSON literal in an inline <script>. Returns the parsed dict
        (with int post_id / episode_id) or None if not found / unparseable.
        """
        m = re.search(r"var\s+podlove_vue\s*=\s*(\{.*?\})\s*;", html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        try:
            data["post_id"] = int(data["post_id"])
            data["episode_id"] = int(data["episode_id"])
        except (KeyError, ValueError, TypeError):
            return None
        return data

    @staticmethod
    def _format_duration(seconds) -> str:
        try:
            total = int(seconds)
        except (TypeError, ValueError):
            return str(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _update_podlove_episode(self, episode_id: int, info: dict) -> None:
        payload = {
            "title": info["title"],
            "summary": info["comment"],
            "number": int(info["number"]) if str(info["number"]).isdigit() else info["number"],
            "slug": info["slug"],
            "duration": self._format_duration(info["duration"]),
            "type": "full",
        }
        # Дата записи задаётся при оформлении (info["recording_date"], ISO
        # YYYY-MM-DD). Если её нет — не шлём ключ, чтобы Podlove не затирал
        # значение пустотой.
        recording_date = info.get("recording_date")
        if recording_date:
            payload["recording_date"] = recording_date
        self._rest_request("POST", f"/podlove/v2/episodes/{episode_id}", json_body=payload)
        logger.debug(f"Podlove episode {episode_id} metadata updated")

    def _update_podlove_chapters(self, episode_id: int, chapters: list) -> None:
        payload = {"chapters": [{"start": start, "title": title} for start, title in chapters]}
        self._rest_request("POST", f"/podlove/v2/chapters/{episode_id}", json_body=payload)
        logger.debug(f"Podlove episode {episode_id} chapters updated ({len(chapters)} entries)")
