"""Podlove REST API: метаданные эпизода и главы.

Отдельный от wp-admin путь: форму постов мы скрейпим, а Podlove правим
через REST по Application Password. Выделено из ``wordpress`` вместе с
:mod:`wp_http`.
"""

import html
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

    def find_draft(self, post_title: str) -> tuple[int, int] | None:
        """``(post_id, episode_id)`` черновика с заголовком ``post_title`` или None.

        Нужен для идемпотентности: повтор после частичного успеха (пост
        сохранён, а Podlove REST упал) должен дописать тот же черновик, а не
        заводить второй. Список Podlove отдаёт только ``id`` и ``title``,
        ``post_id`` берём из карточки эпизода. Любая ошибка поиска не мешает
        публикации — тогда создаём новый пост, как раньше.
        """
        if self._app_auth is None:
            return None
        try:
            listing = self._rest_request("GET", "/podlove/v2/episodes?status=draft").json()
            for item in listing.get("results", []):
                if html.unescape(str(item.get("title", ""))).strip() != post_title:
                    continue
                episode_id = int(item["id"])
                episode = self._rest_request("GET", f"/podlove/v2/episodes/{episode_id}").json()
                return int(episode["post_id"]), episode_id
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning(f"Draft lookup for {post_title!r} failed, creating a new post: {e!r}")
        return None

    def podcast_rest_path(self, post_id: str) -> str:
        """REST-путь поста типа ``podcast`` для проверки черновика.

        Podlove регистрирует тип с ``rest_base='episodes'`` (не ``podcast``),
        а фильтр ``podlove_post_type_args`` может его поменять — поэтому база
        читается из ``wp/v2/types/podcast``, при сбое берётся ``episodes``.
        """
        rest_base = "episodes"
        if self._app_auth is not None:
            try:
                rest_base = self._rest_request("GET", "/wp/v2/types/podcast").json().get("rest_base") or rest_base
            except (RuntimeError, ValueError, AttributeError) as e:
                logger.warning(f"Could not resolve podcast rest_base, using {rest_base!r}: {e!r}")
        return f"/wp/v2/{rest_base}/{post_id}"

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

    def _restore_post_title(self, post_id: int, post_title: str) -> None:
        """Возвращает заголовку записи вид «Разговорный жанр — N».

        Podlove при сохранении эпизода по REST копирует его ``title`` в
        заголовок записи WordPress, и «N. Название» вытесняет заголовок,
        заданный формой. Поле Title эпизода при этом остаётся как есть.
        Сбой не отменяет публикацию: черновик уже создан, заголовок
        правится руками.
        """
        try:
            self._rest_request("POST", self.podcast_rest_path(str(post_id)), json_body={"title": post_title})
        except RuntimeError as e:
            logger.warning(f"Could not restore post title {post_title!r} for post {post_id}: {e!r}")
            return
        logger.debug(f"Post {post_id} title restored to {post_title!r}")

    def _update_podlove_chapters(self, episode_id: int, chapters: list) -> None:
        payload = {"chapters": [{"start": start, "title": title} for start, title in chapters]}
        self._rest_request("POST", f"/podlove/v2/chapters/{episode_id}", json_body=payload)
        logger.debug(f"Podlove episode {episode_id} chapters updated ({len(chapters)} entries)")
