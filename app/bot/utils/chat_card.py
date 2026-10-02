"""Чат по имени, а не по id: как бот называет админам чат из настроек.

В настройках чат задан username'ом или числовым id. Админу id ничего не
говорит, поэтому бот спрашивает у Telegram название, username и фото чата
(``getChat``) и показывает их:

* в тексте: название ссылкой на ``t.me/<username>`` у публичного чата и жирным
  у приватного (:attr:`ChatCard.html`);
* карточкой под текстом: у публичного чата это превью его ссылки, Telegram сам
  рисует в нём аватар и название (:attr:`ChatCard.preview`);
* фотографией чата с подписью: у приватной группы ссылки для превью нет, а
  ссылку-приглашение показывать нельзя, поэтому сообщение о статусе уходит
  фотографией чата (:func:`send`);
* во всплывающих ответах на кнопки, где разметки нет, названием в кавычках
  (:attr:`ChatCard.quoted`).

Ответ ``getChat`` лежит в Redis десять минут. Если бот не может прочитать чат
(его там нет, чат не найден), остаётся то, что написано в настройках.
"""

import json
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, LinkPreviewOptions, Message
from dialog_engine.integrations.aiogram import DefaultSender, MessageAnchor
from loguru import logger

from config import LOCAL
from services.none_module import _NoneModule
from services.redis import redis

CARD_KEY = "chat:card:{}"
PHOTO_KEY = "chat:photo:{}"
CARD_TTL = 600
# file_id уже отправленной фотографии годится, пока у чата та же фотография:
# ключ кеша — её file_unique_id.
PHOTO_TTL = 30 * 24 * 3600
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


@dataclass(frozen=True)
class ChatCard:
    """Чат из настроек: ``ref`` как в ``.env`` и то, что о нём известно Telegram."""

    ref: str
    title: str | None = None
    username: str | None = None
    photo_id: str | None = None
    photo_key: str | None = None

    @property
    def name(self) -> str:
        """Название простым текстом; чат не прочитался — значение из настроек."""
        return self.title or self.ref

    @property
    def quoted(self) -> str:
        """Для текста без разметки (ответ на нажатие кнопки)."""
        return f"«{self.title}»" if self.title else self.ref

    @property
    def link(self) -> str | None:
        return f"https://t.me/{self.username}" if self.username else None

    @property
    def html(self) -> str:
        """Для HTML-текста: ссылка у публичного чата, жирное название у приватного."""
        if self.title is None:
            return escape(self.ref)
        if self.link:
            return f'<a href="{self.link}">{escape(self.title)}</a>'
        return f"<b>{escape(self.title)}</b>"

    @property
    def preview(self) -> LinkPreviewOptions:
        """Карточка чата под текстом: превью его ссылки с маленьким аватаром."""
        if self.link is None:
            return NO_PREVIEW
        return LinkPreviewOptions(url=self.link, prefer_small_media=True, show_above_text=False)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _cache() -> Any | None:
    return None if isinstance(redis, _NoneModule) else redis


async def _cached(key: str) -> str | None:
    cache = _cache()
    if cache is None:
        return None
    try:
        return _str(await cache.get(key))
    except Exception as error:
        logger.debug(f"chat card: cache read failed: {error!r}")
        return None


async def _remember(key: str, value: str, ttl: int) -> None:
    cache = _cache()
    if cache is None:
        return
    try:
        await cache.set(key, value, ex=ttl)
    except Exception as error:
        logger.debug(f"chat card: cache write failed: {error!r}")


async def resolve(bot: Bot, ref: str | int) -> ChatCard:
    """Карточка чата *ref* (``@username`` или числовой id); не падает никогда."""
    ref = str(ref)
    cached = await _cached(CARD_KEY.format(ref))
    if cached:
        try:
            return ChatCard(**json.loads(cached))
        except (TypeError, ValueError):
            logger.debug(f"chat card: stale cache entry for {ref}")
    try:
        chat = await bot.get_chat(ref)
    except Exception as error:
        logger.info(f"chat card: {ref} is not readable, showing it as configured: {error!r}")
        return ChatCard(ref)
    title = _str(getattr(chat, "title", None)) or _str(getattr(chat, "full_name", None))
    if title is None:
        return ChatCard(ref)
    photo = getattr(chat, "photo", None)
    card = ChatCard(
        ref=ref,
        title=title,
        username=_str(getattr(chat, "username", None)),
        photo_id=_str(getattr(photo, "small_file_id", None)),
        photo_key=_str(getattr(photo, "small_file_unique_id", None)),
    )
    await _remember(CARD_KEY.format(ref), json.dumps(asdict(card), ensure_ascii=False), CARD_TTL)
    return card


async def _photo(bot: Bot, card: ChatCard) -> str | BufferedInputFile | None:
    """Фото чата для отправки: file_id из кеша или сам файл."""
    if card.photo_id is None or card.photo_key is None:
        return None
    sent_before = await _cached(PHOTO_KEY.format(card.photo_key))
    if sent_before:
        return sent_before
    file = await bot.get_file(card.photo_id)
    if LOCAL:
        # Локальный Bot API отдаёт путь на диске, том у него с ботом общий.
        data = Path(file.file_path).read_bytes()
    else:
        buffer = await bot.download_file(file.file_path)
        data = buffer.read()
    return BufferedInputFile(data, filename="chat.jpg")


@dataclass
class CardMessage:
    """Отправленное сообщение с карточкой чата: его можно править дальше."""

    message: Message
    card: ChatCard
    with_photo: bool = False

    async def edit(self, text: str) -> None:
        if self.with_photo:
            await self.message.edit_caption(caption=text, parse_mode=ParseMode.HTML)
        else:
            await self.message.edit_text(text, parse_mode=ParseMode.HTML, link_preview_options=self.card.preview)


async def send(bot: Bot, to: Message, card: ChatCard, text: str) -> CardMessage:
    """Ответ на *to* с карточкой чата: фото приватной группы или превью ссылки."""
    if card.link is None:
        try:
            photo = await _photo(bot, card)
            if photo is not None:
                sent = await to.answer_photo(photo, caption=text, parse_mode=ParseMode.HTML)
                if not isinstance(photo, str) and sent.photo:
                    await _remember(PHOTO_KEY.format(card.photo_key), sent.photo[-1].file_id, PHOTO_TTL)
                return CardMessage(sent, card, with_photo=True)
        except Exception as error:
            logger.info(f"chat card: photo of {card.ref} was not sent, falling back to text: {error!r}")
    sent = await to.answer(text, parse_mode=ParseMode.HTML, link_preview_options=card.preview)
    return CardMessage(sent, card)


class CardSender(DefaultSender):
    """Отправка шагов диалога с карточкой чата под текстом."""

    def __init__(self, bot: Bot, chat_id: int | str, card: ChatCard) -> None:
        super().__init__(bot, chat_id)
        self.card = card

    async def _send(self, text: str, keyboard: InlineKeyboardMarkup | None) -> MessageAnchor:
        message = await self.bot.send_message(
            chat_id=self.chat_id, text=text, reply_markup=keyboard, link_preview_options=self.card.preview
        )
        return MessageAnchor(chat_id=message.chat.id, message_id=message.message_id)

    async def _edit(self, anchor: MessageAnchor, text: str, keyboard: InlineKeyboardMarkup | None) -> None:
        await self.bot.edit_message_text(
            chat_id=anchor.chat_id,
            message_id=anchor.message_id,
            text=text,
            reply_markup=keyboard,
            link_preview_options=self.card.preview,
        )
