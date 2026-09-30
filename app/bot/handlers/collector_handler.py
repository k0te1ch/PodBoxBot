"""Заметки ведущих: приём сообщений и просмотр в меню.

* ``/note #тема текст`` — ведущий (админ) пишет заметку боту в личку.

Просмотр — из /admin: группа (хештег) → список записей постранично → карточка
с кнопками «Использовано» и «Удалить». Использованные уходят из списка в архив.
"""

import html
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger
from sagenza_tgbot_sdk.menus import ListItem, ListMenu, MenuContext, Submenu
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback

from config import NOTE_TAGS, TIMEZONE
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import redis
from services.collector import Entry, EntryStore, pick_tag, strip_hashtags
from services.i18n import t

PREVIEW_CHARS = 40


@dataclass
class Collection:
    """Одна коллекция записей и её пара меню: группы и записи группы."""

    name: str
    tags: list[str]
    default_tag: str

    @property
    def groups_menu(self) -> str:
        return f"{self.name}_groups"

    @property
    def entries_menu(self) -> str:
        return f"{self.name}_entries"

    @property
    def state_key(self) -> str:
        return f"{self.name}_tag"

    @property
    def store(self) -> EntryStore:
        return EntryStore(redis, f"collector:{self.name}")


NOTES = Collection("notes", NOTE_TAGS, NOTE_TAGS[-1] if NOTE_TAGS else "note")
COLLECTIONS = {c.name: c for c in (NOTES,)}


class EntryCallback(CallbackData, prefix="col"):
    c: str
    a: str
    id: int
    p: int = 0


def _state(ctx_data: dict[str, Any]) -> FSMContext | None:
    state = ctx_data.get("state")
    return state if isinstance(state, FSMContext) else None


async def _current_tag(collection: Collection, data: dict[str, Any]) -> str:
    state = _state(data)
    if state is not None:
        tag = (await state.get_data()).get(collection.state_key)
        if tag in collection.tags:
            return tag
    return collection.tags[0] if collection.tags else collection.default_tag


def _preview(entry: Entry) -> str:
    text = " ".join(entry.text.split())
    if len(text) > PREVIEW_CHARS:
        text = text[: PREVIEW_CHARS - 1] + "…"
    return f"{datetime.fromtimestamp(entry.created_at, TIMEZONE):%d.%m} {text}"


def card_text(entry: Entry, ctx: MenuContext) -> str:
    when = datetime.fromtimestamp(entry.created_at, TIMEZONE)
    lines = [f"<b>#{html.escape(entry.tag)}</b> · {html.escape(entry.author)} · {when:%d.%m.%Y %H:%M}", ""]
    lines.append(html.escape(entry.text))
    if entry.link:
        lines += ["", f'<a href="{entry.link}">{ctx.text("collector_open_message")}</a>']
    return "\n".join(lines)


def card_markup(collection: Collection, entry: Entry, ctx: MenuContext) -> InlineKeyboardMarkup:
    def action(key: str, name: str) -> InlineKeyboardButton:
        data = EntryCallback(c=collection.name, a=name, id=entry.id, p=ctx.page).pack()
        return InlineKeyboardButton(text=ctx.text(key), callback_data=data)

    back = MenuCallback(m=collection.entries_menu, a=Action.OPEN, p=ctx.page).pack()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [action("collector_used", "used"), action("collector_delete", "del")],
            [InlineKeyboardButton(text=ctx.text("menu-back"), callback_data=back)],
        ]
    )


def build_collection_menu(collection: Collection) -> ListMenu:
    """Меню группы → записи. Записи — дочернее меню со скрытой кнопкой:
    так у него есть «Назад» к группам, а открывается оно из on_select."""

    async def groups(ctx: MenuContext) -> list[ListItem]:
        items = []
        for tag in collection.tags:
            count = await collection.store.count(tag)
            items.append(ListItem(id=str(collection.tags.index(tag)), text=f"#{tag} ({count})"))
        return items

    async def entries(ctx: MenuContext) -> list[ListItem]:
        tag = await _current_tag(collection, ctx.data)
        return [ListItem(id=str(entry.id), text=_preview(entry)) for entry in await collection.store.list(tag)]

    async def open_group(ctx: MenuContext) -> None:
        state = _state(ctx.data)
        index = int(ctx.value or 0)
        if state is not None and 0 <= index < len(collection.tags):
            await state.update_data({collection.state_key: collection.tags[index]})
        await ctx.show(collection.entries_menu)

    async def open_entry(ctx: MenuContext) -> None:
        entry = await collection.store.get(int(ctx.value or 0))
        if entry is None:
            await ctx.answer(ctx.text("collector_missing"), alert=True)
            await ctx.show(collection.entries_menu, ctx.page)
            return
        await ctx.answer()
        await ctx.put(card_text(entry, ctx), card_markup(collection, entry, ctx))

    entries_menu = ListMenu(
        collection.entries_menu, source=entries, on_select=open_entry, title=f"{collection.name}_entries", page_size=8
    )
    return ListMenu(
        collection.groups_menu,
        source=groups,
        on_select=open_group,
        title=f"{collection.name}_groups",
        items=[Submenu(f"{collection.name}_entries", entries_menu, id="entries", visible_if=lambda _ctx: False)],
    )


def collection_submenus(visible_if) -> list[Submenu]:
    return [
        Submenu(f"admin_{c.name}", build_collection_menu(c), id=c.name, visible_if=visible_if)
        for c in COLLECTIONS.values()
    ]


def _author(message: Message) -> str:
    user = message.from_user
    if user is None:
        return message.chat.title or "?"
    return f"@{user.username}" if user.username else user.full_name


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(Command("note"), IsPrivate, IsAdmin)
async def add_note(msg: Message, command: CommandObject, language: str):
    await _save_from_command(msg, command, NOTES, language)


async def _save_from_command(msg: Message, command: CommandObject, collection: Collection, language: str) -> None:
    raw = command.args or ""
    tag = pick_tag(raw, collection.tags) or collection.default_tag
    text = strip_hashtags(raw, [tag])
    if not text:
        await msg.answer(t(f"{collection.name}_usage", language, tags=_tags_hint(collection)))
        return
    entry = await collection.store.add(Entry(tag=tag, text=text, author=_author(msg)))
    logger.info(f"Collected {collection.name} #{entry.id if entry else '?'} in #{tag}")
    await msg.answer(t("collector_saved", language, tag=tag))


def _tags_hint(collection: Collection) -> str:
    return " ".join(f"#{tag}" for tag in collection.tags)


@router.callback_query(EntryCallback.filter(), IsAdmin)
async def entry_action(callback: CallbackQuery, callback_data: EntryCallback, state: FSMContext):
    from handlers.menus import menus

    collection = COLLECTIONS.get(callback_data.c)
    if collection is None:
        await callback.answer()
        return
    ctx = menus.context(callback, {"state": state})
    if callback_data.a == "used":
        done = await collection.store.mark_used(callback_data.id) is not None
        key = "collector_marked_used"
    else:
        done = await collection.store.delete(callback_data.id)
        key = "collector_deleted"
    await ctx.answer(ctx.text(key if done else "collector_missing"))
    await ctx.show(collection.entries_menu, callback_data.p)
