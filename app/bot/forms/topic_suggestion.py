"""Анкета «Предложить тему»: текст темы → подтверждение.

В группе анкета идёт эфемерными сообщениями (их видит только автор), в личке
бота — обычными. Шаги одни и те же, отличается только раскладка: в группе
``force_reply`` открывает у автора поле ответа, и ответ тоже уходит эфемерно.
Проверка длины — та же, что у тем по хештегу (:class:`services.topics.TopicService`).
Отправку в очередь и ответы делает :mod:`handlers.topics_form_handler`.
"""

import html
from datetime import timedelta
from typing import Any

from dialog_engine import DialogEngine, StepContext, ValidationError
from dialog_engine.integrations.aiogram import DialogRunner, FSMDialogStorage, KeyboardLayout

import config as bot_config
from services.i18n import t
from services.topics.runtime import topic_service

DIALOG_ID = "topic_suggestion"
TEXT = "text"
CONFIRM = "confirm"

SESSION_TTL = timedelta(minutes=30)

# Тексты движка про конец сессии зовут к /start — анкете тем нужен свой.
_OWN_KEYS = {"de.alert.no_session": "topics_form_expired", "de.alert.expired": "topics_form_expired"}


def check_topic(value: str, ctx: StepContext) -> str:
    """Та же проверка длины, что у тем из чата; в ответ — текст без лишних пробелов."""
    text = " ".join(str(value).split())
    refusal = topic_service().check_text(text)
    if refusal is not None:
        raise ValidationError(f"topics_refused_{refusal}", ctx.step.id)
    return text


def resolve_text(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str:
    """Ключ схемы → строка из ``locales/*.ftl``; неизвестный ключ движок заменит своим текстом."""
    lookup = _OWN_KEYS.get(key) or (key.replace(".", "-") if key.startswith("de.") else key)
    text = t(
        lookup,
        context.get("lang", "ru"),
        topic=html.escape(str(answers.get(TEXT, ""))),
        min=bot_config.TOPICS_MIN_LENGTH,
        max=bot_config.TOPICS_MAX_LENGTH,
    )
    return key if text == lookup else text


topic_suggestion_engine = DialogEngine.from_list(
    [
        {"id": TEXT, "type": "text", "text": "topics_form_ask"},
        {"id": CONFIRM, "type": "confirm", "text": "topics_form_confirm", "choices": {}},
    ],
    dialog_id=DIALOG_ID,
    text_resolver=resolve_text,
    validators={TEXT: check_topic},
    ttl=SESSION_TTL,
)

storage = FSMDialogStorage.for_engine(topic_suggestion_engine)
group_runner = DialogRunner(
    topic_suggestion_engine,
    layout=KeyboardLayout(row_width=2, show_cancel=True, force_reply=True),
    storage=storage,
)
private_runner = DialogRunner(
    topic_suggestion_engine,
    layout=KeyboardLayout(row_width=2, show_cancel=True),
    storage=storage,
)
