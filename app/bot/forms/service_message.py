"""Диалог сервисного сообщения: текст → когда → подтверждение → отправка в чат.

Админ пишет боту текст, бот спрашивает «Отправить в чат?», и после
подтверждения текст уходит в ``FORWARD_CHAT_USERNAME``. Отправку делает
:mod:`handlers.service_handler`, здесь только шаги диалога.
"""

from datetime import timedelta
from html import escape
from typing import Any

from dialog_engine import DialogEngine, StepContext, ValidationError
from dialog_engine.integrations.aiogram import DialogRunner, KeyboardLayout

from config import FORWARD_CHAT_USERNAME
from services.i18n import t
from services.scheduled_messages import parse_schedule

DIALOG_ID = "service_message"
TEXT = "text"
WHEN = "when"
CONFIRM = "confirm"

SESSION_TTL = timedelta(hours=1)


def resolve_text(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str:
    """Ключ схемы → строка из ``locales/*.ftl``; неизвестный ключ движок заменит своим текстом."""
    lookup = key.replace(".", "-") if key.startswith("de.") else key
    # Как назвать чат, решает хендлер: он спрашивает у Telegram название.
    chat = context.get("chat") or escape(FORWARD_CHAT_USERNAME)
    lang = context.get("lang", "ru")
    schedule = parse_schedule(str(answers.get(WHEN) or ""))
    text = t(lookup, lang, chat=chat, when=schedule.human(lang) if schedule else "")
    return key if text == lookup else text


async def check_when(value: str, ctx: StepContext) -> str:
    """«Когда отправить»: сейчас, дата со временем или повтор; в ответе нормализованная строка."""
    schedule = parse_schedule(str(value))
    if schedule is None:
        raise ValidationError("invalid_service_when", ctx.step.id)
    return schedule.encode()


service_message_engine = DialogEngine.from_list(
    [
        {"id": TEXT, "type": "text", "text": "service_ask_text"},
        {"id": WHEN, "type": "text", "text": "service_ask_when"},
        {"id": CONFIRM, "type": "confirm", "text": "service_confirm", "choices": {}},
    ],
    dialog_id=DIALOG_ID,
    text_resolver=resolve_text,
    validators={WHEN: check_when},
    ttl=SESSION_TTL,
)

service_message_runner = DialogRunner(service_message_engine, layout=KeyboardLayout(row_width=2, show_cancel=True))
