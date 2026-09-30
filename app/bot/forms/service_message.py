"""Диалог сервисного сообщения: текст → подтверждение → отправка в чат.

Админ пишет боту текст, бот спрашивает «Отправить в чат?», и после
подтверждения текст уходит в ``FORWARD_CHAT_USERNAME``. Отправку делает
:mod:`handlers.service_handler`, здесь только шаги диалога.
"""

from datetime import timedelta
from typing import Any

from dialog_engine import DialogEngine
from dialog_engine.integrations.aiogram import DialogRunner, KeyboardLayout

from config import FORWARD_CHAT_USERNAME
from services.i18n import t

DIALOG_ID = "service_message"
TEXT = "text"
CONFIRM = "confirm"

SESSION_TTL = timedelta(hours=1)


def resolve_text(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str:
    """Ключ схемы → строка из ``locales/*.ftl``; неизвестный ключ движок заменит своим текстом."""
    lookup = key.replace(".", "-") if key.startswith("de.") else key
    text = t(lookup, context.get("lang", "ru"), chat=FORWARD_CHAT_USERNAME)
    return key if text == lookup else text


service_message_engine = DialogEngine.from_list(
    [
        {"id": TEXT, "type": "text", "text": "service_ask_text"},
        {"id": CONFIRM, "type": "confirm", "text": "service_confirm", "choices": {}},
    ],
    dialog_id=DIALOG_ID,
    text_resolver=resolve_text,
    ttl=SESSION_TTL,
)

service_message_runner = DialogRunner(service_message_engine, layout=KeyboardLayout(row_width=2, show_cancel=True))
