"""Анкета «Предложить тему или вопрос»: тип → текст → подтверждение.

Анкет две, шаги у них общие:

* :data:`FULL` начинает с выбора типа (тема или вопрос): так открывается
  анкета в группе и по ссылке ``?start=topic``;
* :data:`TYPED` сразу просит текст: тип уже известен по команде (``/тема``,
  ``/вопрос``) или кнопке админа и лежит в контексте сессии.

В группе анкета идёт эфемерными сообщениями (их видит только автор), в личке
бота — обычными. Отличается только раскладка: в группе ``force_reply``
открывает у автора поле ответа, и ответ тоже уходит эфемерно. Проверка длины
та же, что у сообщений с хештегом (:class:`services.topics.TopicList`).
Запись в список и ответы делает :mod:`handlers.topics_form_handler`.
"""

import html
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from dialog_engine import DialogEngine, StepContext, ValidationError
from dialog_engine.integrations.aiogram import DialogRunner, FSMDialogStorage, KeyboardLayout

import config as bot_config
from services.i18n import t
from services.topics.models import Kind
from services.topics.runtime import topic_list

DIALOG_ID = "topic_suggestion"
TYPED_DIALOG_ID = "topic_suggestion_typed"
KIND = "kind"
TEXT = "text"
CONFIRM = "confirm"

SESSION_TTL = timedelta(minutes=30)

# Тексты движка про конец сессии зовут к /start — анкете нужен свой.
_OWN_KEYS = {"de.alert.no_session": "topics_form_expired", "de.alert.expired": "topics_form_expired"}
# Вопрос анкеты зависит от типа пункта («Какую тему…» или «Какой вопрос…») и от
# того, кто спрашивает: админу не нужна минимальная длина.
_BY_KIND = {"topics_form_ask"}


def kind_of(answers: dict[str, Any], context: dict[str, Any]) -> Kind:
    """Тип пункта: выбран в анкете или известен заранее из контекста."""
    try:
        return Kind(answers.get(KIND) or context.get(KIND))
    except ValueError:
        return Kind.TOPIC


def check_text(value: str, ctx: StepContext) -> str:
    """Та же проверка длины, что у сообщений из чата; в ответ — текст без лишних пробелов."""
    text = " ".join(str(value).split())
    refusal = topic_list().check_text(text, trusted=bool(ctx.context.get("trusted")))
    if refusal is not None:
        raise ValidationError(f"topics_refused_{refusal}", ctx.step.id)
    return text


def resolve_text(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str:
    """Ключ схемы → строка из ``locales/*.ftl``; неизвестный ключ движок заменит своим текстом."""
    locale = context.get("lang", "ru")
    kind = kind_of(answers, context)
    lookup = _OWN_KEYS.get(key) or (key.replace(".", "-") if key.startswith("de.") else key)
    if lookup in _BY_KIND:
        lookup = f"{lookup}_{kind}" + ("_admin" if context.get("trusted") else "")
    text = t(
        lookup,
        locale,
        kind=t(f"topics_kind_{kind}", locale),
        text=html.escape(str(answers.get(TEXT, ""))),
        min=1 if context.get("trusted") else bot_config.TOPICS_MIN_LENGTH,
        max=bot_config.TOPICS_MAX_LENGTH,
    )
    return key if text == lookup else text


_KIND_STEP = {
    "id": KIND,
    "type": "choice",
    "text": "topics_form_kind",
    "choices": {Kind.TOPIC.value: "topics_form_kind_topic", Kind.QUESTION.value: "topics_form_kind_question"},
}
_TEXT_STEPS = [
    {"id": TEXT, "type": "text", "text": "topics_form_ask"},
    {"id": CONFIRM, "type": "confirm", "text": "topics_form_confirm", "choices": {}},
]


@dataclass(frozen=True)
class Form:
    """Анкета и два её раннера: для группы и для лички."""

    dialog_id: str
    storage: FSMDialogStorage
    group_runner: DialogRunner
    private_runner: DialogRunner

    def runner(self, in_group: bool) -> DialogRunner:
        return self.group_runner if in_group else self.private_runner


def _form(dialog_id: str, steps: list[dict[str, Any]]) -> Form:
    engine = DialogEngine.from_list(
        steps,
        dialog_id=dialog_id,
        text_resolver=resolve_text,
        validators={TEXT: check_text},
        ttl=SESSION_TTL,
    )
    storage = FSMDialogStorage.for_engine(engine)
    return Form(
        dialog_id,
        storage,
        group_runner=DialogRunner(
            engine, layout=KeyboardLayout(row_width=2, show_cancel=True, force_reply=True), storage=storage
        ),
        private_runner=DialogRunner(engine, layout=KeyboardLayout(row_width=2, show_cancel=True), storage=storage),
    )


FULL = _form(DIALOG_ID, [_KIND_STEP, *_TEXT_STEPS])
TYPED = _form(TYPED_DIALOG_ID, _TEXT_STEPS)
FORMS = (FULL, TYPED)
