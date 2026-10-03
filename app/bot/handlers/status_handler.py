"""``/status``: что с ботом и с последними публикациями, таблицей.

Вместо ``/status`` из SDK (версия SDK, аптайм и счётчики): админу важнее
версия бота, что включено и чем кончились последние публикации.
"""

import os
import time
from datetime import timedelta
from html import escape
from typing import Any

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger

import config as bot_config
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services.i18n import t
from services.metrics import bot_metrics
from services.publish_board import Board, boards, platform_title
from services.topics.runtime import topic_list, topics_enabled
from utils import rich
from utils.release_notes import get_version

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)

STARTED = time.monotonic()
MAX_PUBLICATIONS = 5


def _yes(flag: object, locale: str) -> str:
    return t("status_on" if flag else "status_off", locale)


async def _facts(metrics: Any, locale: str) -> list[tuple[str, str]]:
    """Строки таблицы «параметр, значение»."""
    try:
        version = await get_version()
    except Exception as e:
        logger.debug(f"status: version is unknown: {e!r}")
        version = None
    facts = [
        (t("status_version", locale), version or "?"),
        (t("status_uptime", locale), str(timedelta(seconds=int(time.monotonic() - STARTED)))),
    ]
    if metrics is not None:
        totals = metrics.totals()
        facts.append((t("status_updates", locale), f"{totals['updates']:.0f}"))
        facts.append((t("status_errors", locale), f"{totals['errors']:.0f}"))
    facts.append((t("status_rss", locale), _yes(bot_config.RSS_FEED_URL, locale)))
    if topics_enabled():
        try:
            count = str(len(await topic_list().repository.items()))
        except Exception as e:
            logger.warning(f"status: the topics list is not readable: {e!r}")
            count = "?"
        facts.append((t("status_topics", locale), count))
    else:
        facts.append((t("status_topics", locale), _yes(False, locale)))
    return facts


def _publication_rows(recent: list[Board]) -> list[list[str]]:
    return [
        [escape(board.title.split(":")[0]), escape(platform_title(row.platform)), row.text, board.when(row)]
        for board in recent
        for row in board.rows.values()
    ]


async def render(metrics: Any, locale: str) -> tuple[str, str]:
    """``/status`` rich-сообщением и тем же обычным текстом."""
    facts = await _facts(metrics, locale)
    html = f"<h4>{escape(t('status_title', locale))}</h4>" + rich.table(
        [t("status_column_what", locale), t("status_column_value", locale)],
        [[escape(name), escape(value)] for name, value in facts],
    )
    text = "\n".join([f"<b>{escape(t('status_title', locale))}</b>", *(f"{escape(n)}: {escape(v)}" for n, v in facts)])
    rows = _publication_rows(await boards.recent(MAX_PUBLICATIONS))
    heading = t("status_publications", locale)
    if rows:
        columns = [t(f"status_column_{name}", locale) for name in ("episode", "platform", "state", "when")]
        html += f"<h4>{escape(heading)}</h4>" + rich.table(columns, rows)
        text += f"\n\n<b>{escape(heading)}</b>\n" + "\n".join(" · ".join(row) for row in rows)
    else:
        none = t("status_publications_none", locale)
        html += f"<p>{escape(none)}</p>"
        text += f"\n\n{escape(none)}"
    return html, text


@router.message(Command("status"))
async def status(msg: Message, bot: Bot, language: str, metrics: Any = None):
    bot_metrics.admin_action("status")
    html, text = await render(metrics, language)
    await rich.send(bot, msg.chat.id, html, text)
