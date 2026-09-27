"""Клиент официального VK API для поста VK Donut на стене сообщества.

Почему так, а не иначе:

* Раздел аудио закрыт для сторонних приложений с 2016 года, а загрузка через
  внутренние запросы vk.com (al_audio.php с хэшами страницы) ломалась в
  прошлой версии бота раз в месяц: VK меняет хэши. Поэтому только
  официальные методы.
* Методов загрузки подкастов у API нет (podcasts.* только читают каталог).
* Остаются два официальных носителя звука:
  - ``video`` (по умолчанию): mp3 склеивается с обложкой в mp4 (ffmpeg) и
    грузится ``video.save`` в видеозаписи сообщества — плеер прямо в посте;
  - ``doc``: mp3 грузится документом (``docs.getWallUploadServer`` →
    ``docs.save``) — файл скачивается, но плеера нет, и VK может отказать
    в приёме mp3 как документа.
* Замок ставит ``wall.post`` с ``donut_paid_duration``: -1 — навсегда только
  для донов, N — пост откроется всем через N дней.

Токен — пользовательский токен админа сообщества с правами
``wall,video,docs,offline`` (с offline он не истекает, пока не сменят пароль
или не отзовут доступ). Ошибки авторизации и прав — :class:`VkAuthError`
(PermanentError), повторять их бессмысленно.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
from loguru import logger
from sagenza_tgbot_sdk.resilience import PermanentError

API_URL = "https://api.vk.com/method"
_TIMEOUT = httpx.Timeout(60.0, read=600.0, write=600.0)

# Коды, которые повтор не исправит: авторизация, права, неверные параметры,
# запрет публикации. Остальные (6 — слишком часто, 10 — внутренняя ошибка)
# повторяются.
_AUTH_CODES = {5, 7, 15, 27, 28, 200, 203, 214, 219}
_PERMANENT_CODES = {100, 113, 1051}


class VkApiError(RuntimeError):
    def __init__(self, method: str, code: int, message: str) -> None:
        super().__init__(f"VK {method}: [{code}] {message}")
        self.code = code


class VkAuthError(VkApiError, PermanentError):
    HINT = (
        "Проверьте VK_ACCESS_TOKEN: нужен пользовательский токен админа сообщества "
        "с правами wall, video, docs, offline (см. app/publishers/VK/SMOKE.md)."
    )

    def __str__(self) -> str:
        return f"{super().__str__()}. {self.HINT}"


class VkPermanentError(VkApiError, PermanentError):
    pass


def _raise_for_error(method: str, body: dict) -> None:
    error = body.get("error")
    if not error:
        return
    code = int(error.get("error_code", 0))
    message = str(error.get("error_msg", error))
    if code in _AUTH_CODES:
        raise VkAuthError(method, code, message)
    if code in _PERMANENT_CODES:
        raise VkPermanentError(method, code, message)
    raise VkApiError(method, code, message)


async def mp3_to_video(mp3: str, cover: str, out: str) -> None:
    """Склеивает mp3 и статичную обложку в mp4 для video.save."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-i",
        cover,
        "-i",
        mp3,
        "-vf",
        "scale=1280:-2",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        out,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise PermanentError(f"ffmpeg failed ({process.returncode}): {stderr.decode(errors='replace')[-500:]}")


class VkClient:
    def __init__(
        self,
        token: str | None,
        group_id: int | None,
        version: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.group_id = group_id
        self.version = version
        self.http = http or httpx.AsyncClient(timeout=_TIMEOUT)

    def check_config(self) -> None:
        if not self.token:
            raise VkAuthError("config", 5, "VK_ACCESS_TOKEN не задан")
        if not self.group_id:
            raise VkPermanentError("config", 100, "VK_GROUP_ID не задан")

    async def call(self, method: str, **params) -> dict | list:
        self.check_config()
        data = {k: v for k, v in params.items() if v is not None}
        data.update(access_token=self.token, v=self.version)
        resp = await self.http.post(f"{API_URL}/{method}", data=data)
        resp.raise_for_status()
        body = resp.json()
        _raise_for_error(method, body)
        return body["response"]

    async def _upload_file(self, url: str, field: str, path: str, content_type: str) -> dict:
        content = await asyncio.to_thread(Path(path).read_bytes)
        resp = await self.http.post(url, files={field: (Path(path).name, content, content_type)})
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise VkApiError("upload", 0, str(body.get("error")))
        return body

    async def upload_video(self, mp3: str, cover: str, title: str, description: str) -> str:
        """mp3 + обложка → видеозапись сообщества. Возвращает ``video<owner>_<id>``."""
        self.check_config()
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "episode.mp4")
            await mp3_to_video(mp3, cover, out)
            saved = await self.call(
                "video.save",
                group_id=self.group_id,
                name=title,
                description=description,
                wallpost=0,
                no_comments=0,
            )
            await self._upload_file(saved["upload_url"], "video_file", out, "video/mp4")
        owner_id = saved.get("owner_id", -int(self.group_id))
        return f"video{owner_id}_{saved['video_id']}"

    async def upload_doc(self, mp3: str, title: str) -> str:
        """mp3 документом сообщества. Возвращает ``doc<owner>_<id>``."""
        server = await self.call("docs.getWallUploadServer", group_id=self.group_id)
        uploaded = await self._upload_file(server["upload_url"], "file", mp3, "audio/mpeg")
        saved = await self.call("docs.save", file=uploaded["file"], title=title)
        doc = saved.get("doc") if isinstance(saved, dict) else saved[0]
        return f"doc{doc['owner_id']}_{doc['id']}"

    async def post(self, message: str, attachments: list[str], donut_paid_duration: int) -> str:
        """Пост на стене сообщества только для донов. Возвращает post_id."""
        resp = await self.call(
            "wall.post",
            owner_id=-int(self.group_id),
            from_group=1,
            message=message,
            attachments=",".join(attachments) or None,
            donut_paid_duration=donut_paid_duration,
        )
        post_id = str(resp["post_id"])
        logger.success(f"VK Donut post published (id={post_id})")
        return post_id

    async def get_post(self, post_id: str) -> dict | None:
        resp = await self.call("wall.getById", posts=f"-{self.group_id}_{post_id}")
        items = resp.get("items", []) if isinstance(resp, dict) else resp
        return items[0] if items else None

    async def get_group(self) -> dict:
        """Сообщество и права токена (для смоука)."""
        resp = await self.call("groups.getById", group_id=self.group_id, fields="donut")
        groups = resp.get("groups", []) if isinstance(resp, dict) else resp
        return groups[0] if groups else {}

    def post_url(self, post_id: str) -> str:
        return f"https://vk.com/wall-{self.group_id}_{post_id}"
