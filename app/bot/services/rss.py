"""Слежение за RSS подкаста: новый эпизод → вопрос админам «Выложить?».

Лента читается раз в ``RSS_POLL_INTERVAL`` секунд. Всё состояние в Redis,
чтобы после рестарта не прислать то же самое ещё раз:

* ``rss:seen`` — guid уже обработанных эпизодов;
* ``rss:initialized`` — первый опрос прошёл. Первый опрос только запоминает
  всю ленту и молчит, иначе админам пришёл бы весь архив;
* ``rss:published`` — номера эпизодов, которые бот выложил сам через /start,
  их в ленте не предлагаем;
* ``rss:episode:<key>`` — данные эпизода для кнопок уведомления (в
  callback_data влезает только короткий ключ);
* ``rss:etag`` / ``rss:last_modified`` — условный запрос, чтобы не качать
  неизменную ленту.

Без Redis слежение не запускается: дедупликация без него теряется при
каждом рестарте.
"""

import asyncio
import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from redis.asyncio import Redis

from services.i18n import t

SEEN_KEY = "rss:seen"
INITIALIZED_KEY = "rss:initialized"
PUBLISHED_KEY = "rss:published"
ETAG_KEY = "rss:etag"
LAST_MODIFIED_KEY = "rss:last_modified"
EPISODE_KEY = "rss:episode:{}"

# Кнопки уведомления живут месяц — дальше «Выложить?» уже неактуально.
EPISODE_TTL = 30 * 24 * 3600
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=30)

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
# Имя mp3 на сайте то же, что даёт generate_file_name: 0767_rz_26092026.mp3,
# 0123_postshow_….mp3. Оно надёжнее названия: в ленте есть и другие шоу
# (outcast_11092026.mp3 с itunes:episode 5), их номер к нашим отношения не имеет.
FILE_NAME_RE = re.compile(r"(?:^|/)(\d+)_(rz|postshow)_[^/]*\.mp3$", re.IGNORECASE)
FILE_TYPES = {"rz": "main", "postshow": "aftershow"}
TAG_RE = re.compile(r"<[^>]+>")

ACTION_CHAT = "chat"
ACTION_PREPARE = "prepare"
ACTION_SKIP = "skip"


@dataclass
class Episode:
    guid: str
    title: str
    link: str = ""
    description: str = ""
    enclosure_url: str | None = None
    number: str | None = None
    type_episode: str | None = None
    """``main`` / ``aftershow`` по имени mp3; None — не наш выпуск, на площадки не предлагаем."""

    @property
    def key(self) -> str:
        return hashlib.sha1(self.guid.encode(), usedforsecurity=False).hexdigest()[:12]


def _text(item: ElementTree.Element, tag: str) -> str:
    return (item.findtext(tag) or "").strip()


def _plain(value: str) -> str:
    return html.unescape(TAG_RE.sub("", value)).strip()


def _identify(item: ElementTree.Element, enclosure_url: str | None) -> tuple[str | None, str | None]:
    """Номер и тип эпизода: из имени mp3, иначе только номер из itunes:episode."""
    match = FILE_NAME_RE.search(enclosure_url or "")
    if match:
        return str(int(match.group(1))), FILE_TYPES[match.group(2).lower()]
    explicit = _text(item, f"{ITUNES_NS}episode")
    return (explicit if explicit.isdigit() else None), None


def parse_feed(xml: bytes) -> list[Episode]:
    """Эпизоды ленты RSS 2.0 в порядке ленты; элементы без guid и ссылки пропускаются."""
    root = ElementTree.fromstring(xml)  # лента своего сайта, не чужой ввод
    episodes = []
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        guid = _text(item, "guid") or link
        if not guid:
            continue
        enclosure = item.find("enclosure")
        enclosure_url = enclosure.get("url") if enclosure is not None else None
        number, type_episode = _identify(item, enclosure_url)
        description = _text(item, f"{ITUNES_NS}summary") or _text(item, "description")
        episodes.append(
            Episode(
                guid=guid,
                title=title,
                link=link,
                description=_plain(description),
                enclosure_url=enclosure_url,
                number=number,
                type_episode=type_episode,
            )
        )
    return episodes


async def mark_published(redis: Redis | None, number: str) -> None:
    """Запоминает эпизод, выложенный через бота, чтобы лента его не предлагала."""
    if redis is None:
        return
    try:
        await redis.sadd(PUBLISHED_KEY, str(number))
    except Exception as e:
        logger.warning(f"rss: could not mark episode {number} as published: {e!r}")


async def save_episode(redis: Redis, episode: Episode) -> None:
    await redis.set(EPISODE_KEY.format(episode.key), json.dumps(asdict(episode)), ex=EPISODE_TTL)


async def load_episode(redis: Redis, key: str) -> Episode | None:
    raw = await redis.get(EPISODE_KEY.format(key))
    return Episode(**json.loads(raw)) if raw else None


def notification_markup(episode: Episode, locale: str) -> InlineKeyboardMarkup:
    """Кнопки уведомления; «На площадки» — только для нашего выпуска с mp3."""
    rows = [[InlineKeyboardButton(text=t("rss_to_chat", locale), callback_data=f"rss:{ACTION_CHAT}:{episode.key}")]]
    if episode.enclosure_url and episode.type_episode:
        rows.append(
            [InlineKeyboardButton(text=t("rss_prepare", locale), callback_data=f"rss:{ACTION_PREPARE}:{episode.key}")]
        )
    rows.append([InlineKeyboardButton(text=t("rss_skip", locale), callback_data=f"rss:{ACTION_SKIP}:{episode.key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notification_text(episode: Episode, locale: str) -> str:
    text = t("rss_new_episode", locale, number=episode.number or "?", title=episode.title)
    if not (episode.enclosure_url and episode.type_episode):
        text += "\n\n" + t("rss_no_mp3", locale)
    return text


class RssWatcher:
    def __init__(
        self,
        bot: Bot,
        redis: Redis,
        feed_url: str,
        admin_ids: list[int],
        interval: int,
        failure_alert: int,
        locale: str = "ru",
    ) -> None:
        self.bot = bot
        self.redis = redis
        self.feed_url = feed_url
        self.admin_ids = admin_ids
        self.interval = interval
        self.failure_alert = failure_alert
        self.locale = locale
        self.failures = 0

    async def fetch(self) -> bytes | None:
        """Тело ленты или None, если сервер ответил 304 Not Modified."""
        headers = {}
        etag = await self.redis.get(ETAG_KEY)
        last_modified = await self.redis.get(LAST_MODIFIED_KEY)
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        async with (
            aiohttp.ClientSession(timeout=FETCH_TIMEOUT) as session,
            session.get(self.feed_url, headers=headers) as response,
        ):
            if response.status == 304:
                return None
            response.raise_for_status()
            body = await response.read()
            if response.headers.get("ETag"):
                await self.redis.set(ETAG_KEY, response.headers["ETag"])
            if response.headers.get("Last-Modified"):
                await self.redis.set(LAST_MODIFIED_KEY, response.headers["Last-Modified"])
            return body

    async def process(self, episodes: list[Episode]) -> list[Episode]:
        """Отбирает новые эпизоды и помечает их виденными; первый прогон молчит."""
        guids = [e.guid for e in episodes]
        if not await self.redis.exists(INITIALIZED_KEY):
            if guids:
                await self.redis.sadd(SEEN_KEY, *guids)
            await self.redis.set(INITIALIZED_KEY, "1")
            logger.info(f"rss: first run, remembered {len(guids)} episodes without notifying")
            return []
        published = await self.redis.smembers(PUBLISHED_KEY)
        fresh = []
        for episode in episodes:
            if await self.redis.sismember(SEEN_KEY, episode.guid):
                continue
            await self.redis.sadd(SEEN_KEY, episode.guid)
            if episode.type_episode and episode.number in published:
                logger.info(f"rss: episode {episode.number} was published by the bot, skipping")
                continue
            fresh.append(episode)
        return fresh

    async def notify(self, episode: Episode) -> None:
        await save_episode(self.redis, episode)
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(
                    admin_id,
                    notification_text(episode, self.locale),
                    reply_markup=notification_markup(episode, self.locale),
                )
            except Exception as e:
                logger.warning(f"rss: could not notify admin {admin_id}: {e!r}")

    async def poll_once(self) -> list[Episode]:
        body = await self.fetch()
        if body is None:
            return []
        fresh = await self.process(parse_feed(body))
        for episode in fresh:
            logger.info(f"rss: new episode {episode.number}: {episode.title}")
            await self.notify(episode)
        return fresh

    async def tick(self) -> None:
        """Один опрос; ошибки логируются, после ``failure_alert`` подряд — одно письмо админам."""
        try:
            await self.poll_once()
        except Exception as e:
            self.failures += 1
            logger.warning(f"rss: poll #{self.failures} failed: {e!r}")
            if self.failures == self.failure_alert:
                await self._alert(t("rss_feed_down", self.locale, count=self.failures, url=self.feed_url))
            return
        self.failures = 0

    async def _alert(self, text: str) -> None:
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception as e:
                logger.warning(f"rss: could not alert admin {admin_id}: {e!r}")

    async def run(self) -> None:
        logger.info(f"rss: watching {self.feed_url} every {self.interval}s")
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)
