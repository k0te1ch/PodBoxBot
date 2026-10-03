"""Диалог загрузки эпизода на :mod:`dialog_engine`.

Три шага: тип эпизода, MP3, шаблон с описанием. Порядок шагов, проверку
ответов, кнопки «Назад»/«Отмена» и хранение сессии в FSM ведёт
:class:`~dialog_engine.integrations.aiogram.DialogRunner`; хендлеры в
:mod:`handlers.podcast_handler` делают то, что движку знать не положено:
скачивают MP3, ставят теги и отправляют готовый файл.

Контекст сессии (сохраняется вместе с ней, поэтому только JSON):

* ``lang`` — язык текстов;
* ``pending_mp3`` — mp3, с которого начали выпуск (прислали без меню): после
  выбора типа он принимается без повторной отправки;
* ``number`` — номер следующего эпизода, его хендлер кладёт после скачивания
  MP3, и он подставляется в шаблон;
* ``mp3_size`` — размер скачанного файла текстом, для строки «файл получен».
"""

from datetime import timedelta
from typing import Any

from dialog_engine import DialogEngine, StepContext, ValidationError
from dialog_engine.integrations.aiogram import DialogRunner, KeyboardLayout

from services.i18n import t
from utils.validators import invalid_recording_date, validate_template

# ID шагов нужны хендлерам, поэтому они именованные константы.
TYPE_EPISODE = "type_episode"
MP3 = "mp3"
TEMPLATE = "template"

DIALOG_ID = "upload_file"
PENDING_MP3 = "pending_mp3"

# Local Bot API отдаёт файлы до 2000 МБ — больше Telegram не пропустит.
MP3_MAX_SIZE = 2000 * 1024 * 1024

# Брошенная загрузка не должна висеть в Redis вечно.
SESSION_TTL = timedelta(hours=6)


async def check_template(value: str, ctx: StepContext) -> dict[str, Any]:
    """Валидатор шага шаблона: разобранные поля эпизода или ошибка на шаге."""
    if invalid_recording_date(value) is not None:
        raise ValidationError("invalid_recording_date", ctx.step.id)
    info = validate_template(value)
    if info is None:
        raise ValidationError("invalid_input", ctx.step.id)
    return info


def resolve_text(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str:
    """Резолвер текстов движка: ключ из схемы → строка из ``locales/*.ftl``.

    Служебные ключи движка (``de.button.cancel``) ищутся с дефисами вместо
    точек; неизвестный ключ возвращается как есть — тогда движок берёт свой
    текст по умолчанию.
    """
    lang = context.get("lang", "ru")
    type_episode = answers.get(TYPE_EPISODE, "main")
    if key == "ask_template":
        key = f"ask_template_{type_episode}"
    if key == "ask_typeEpisode" and context.get(PENDING_MP3):
        key = "ask_typeEpisode_for_file"
    params = {
        "type_episode": t("main_episode" if type_episode == "main" else "episode_aftershow", lang),
        "number": context.get("number", ""),
    }
    lookup = key.replace(".", "-") if key.startswith("de.") else key
    text = t(lookup, lang, **params)
    if lookup.startswith("ask_template_"):
        # Сообщение о загрузке mp3 превращается в этот вопрос: итог загрузки
        # остаётся в нём первой строкой.
        intro = t("downloaded", lang, size=context.get("mp3_size", ""), number=params["number"])
        return f"{intro}\n{text}"
    return key if text == lookup else text


upload_file_engine = DialogEngine.from_list(
    [
        {
            "id": TYPE_EPISODE,
            "type": "choice",
            "text": "ask_typeEpisode",
            "choices": {"main": "main_episode", "aftershow": "episode_aftershow"},
        },
        {
            "id": MP3,
            "type": "file",
            "text": "ask_mp3",
            "mime_types": ["audio/mpeg"],
            "extensions": [".mp3"],
            "max_size": MP3_MAX_SIZE,
        },
        {
            "id": TEMPLATE,
            "type": "text",
            "text": "ask_template",
        },
    ],
    dialog_id=DIALOG_ID,
    text_resolver=resolve_text,
    validators={TEMPLATE: check_template},
    ttl=SESSION_TTL,
)

upload_file_runner = DialogRunner(upload_file_engine, layout=KeyboardLayout(row_width=2, show_cancel=True))
