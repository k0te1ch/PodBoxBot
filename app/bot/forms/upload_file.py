"""Диалог загрузки эпизода на :mod:`dialog_engine`.

Пять шагов: тип эпизода, MP3, дата записи, дата публикации, шаблон с
описанием. Даты выбираются кнопками (:mod:`utils.date_picker`) или пишутся
текстом. Порядок шагов, проверку
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

Ответы шагов дат: дата записи ``YYYY-MM-DD``, публикация ``YYYY-MM-DDTHH:MM``
или пустая строка («как обычно»: площадки работают по своим настройкам).
"""

from datetime import datetime, timedelta
from typing import Any

from dialog_engine import DialogEngine, StepContext, ValidationError
from dialog_engine.integrations.aiogram import DialogRunner, KeyboardLayout

from config import TIMEZONE
from services.i18n import t
from utils import date_picker
from utils.validators import invalid_recording_date, validate_template

# ID шагов нужны хендлерам, поэтому они именованные константы.
TYPE_EPISODE = "type_episode"
MP3 = "mp3"
RECORDING_DATE = "recording_date"
PUBLISH_AT = "publish_at"
TEMPLATE = "template"

# Шаги с выбором даты кнопками: что именно выбирается на шаге.
DATE_STEPS = {RECORDING_DATE: date_picker.RECORDING, PUBLISH_AT: date_picker.PUBLISH}

DIALOG_ID = "upload_file"
PENDING_MP3 = "pending_mp3"
PUBLISH_DAY = "publish_day"
"""День публикации, выбранный кнопкой, пока под вопросом стоят слоты времени:
к нему относится время, набранное сообщением. В контексте диалога."""

# Local Bot API отдаёт файлы до 2000 МБ — больше Telegram не пропустит.
MP3_MAX_SIZE = 2000 * 1024 * 1024

# Брошенная загрузка не должна висеть в Redis вечно.
SESSION_TTL = timedelta(hours=6)


def now() -> datetime:
    """Сейчас в часовом поясе бота, без tzinfo: в нём же админ называет даты."""
    return datetime.now(TIMEZONE).replace(tzinfo=None)


async def check_recording_date(value: str, ctx: StepContext) -> str:
    """Дата записи: из кнопки или текстом, не позже сегодняшнего дня. В ответе ISO."""
    parsed = date_picker.parse_date(str(value))
    if parsed is None or parsed > now().date():
        raise ValidationError("invalid_recording_date", ctx.step.id)
    return parsed.isoformat()


async def check_publish_at(value: str, ctx: StepContext) -> str:
    """Дата и время публикации; пустая строка значит «как обычно».

    Из кнопки приходит дата со временем. Руками можно написать и дату со
    временем, и одно время: оно относится к дню, выбранному кнопкой, а если
    день не выбирали, то к сегодняшнему.
    """
    text = str(value).strip()
    if text.lower() == date_picker.DEFAULT:
        return ""
    parsed = date_picker.parse_datetime(text)
    if parsed is None and (clock := date_picker.parse_time(text)) is not None:
        day = date_picker.parse_date(str(ctx.context.get(PUBLISH_DAY) or "")) or now().date()
        parsed = datetime.combine(day, clock)
    if parsed is None:
        raise ValidationError("invalid_publish_at", ctx.step.id)
    if parsed <= now():
        raise ValidationError("publish_time_passed", ctx.step.id)
    ctx.context.pop(PUBLISH_DAY, None)
    return parsed.strftime(date_picker.DATETIME_FORMAT)


def _recording_text(answers: dict[str, Any], lang: str) -> str:
    parsed = date_picker.parse_date(str(answers.get(RECORDING_DATE) or ""))
    return date_picker.human_date(parsed, lang, today=now().date()) if parsed else ""


def _publish_text(answers: dict[str, Any], lang: str) -> str:
    parsed = date_picker.parse_datetime(str(answers.get(PUBLISH_AT) or ""))
    if parsed is None:
        return t("date_publish_default_short", lang)
    return date_picker.human_datetime(parsed, lang, today=now().date())


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
        "size": context.get("mp3_size", ""),
        "recording": _recording_text(answers, lang),
        "publish": _publish_text(answers, lang),
        "now": f"{now():%H:%M}",
    }
    lookup = key.replace(".", "-") if key.startswith("de.") else key
    text = t(lookup, lang, **params)
    # Сообщение о загрузке mp3 превращается в вопросы о датах и описании: что
    # уже известно о выпуске, остаётся в нём первой строкой.
    summary = SUMMARIES.get("ask_template" if lookup.startswith("ask_template_") else lookup)
    if summary is not None:
        return f"{t(summary, lang, **params)}\n\n{text}"
    return key if text == lookup else text


# Вопрос шага → строка над ним с тем, что о выпуске уже известно.
SUMMARIES = {
    "ask_recording_date": "summary_file",
    "ask_publish_at": "summary_recording",
    "ask_template": "summary_dates",
}


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
        {"id": RECORDING_DATE, "type": "text", "text": "ask_recording_date"},
        {"id": PUBLISH_AT, "type": "text", "text": "ask_publish_at"},
        {
            "id": TEMPLATE,
            "type": "text",
            "text": "ask_template",
        },
    ],
    dialog_id=DIALOG_ID,
    text_resolver=resolve_text,
    validators={RECORDING_DATE: check_recording_date, PUBLISH_AT: check_publish_at, TEMPLATE: check_template},
    ttl=SESSION_TTL,
)

upload_file_runner = DialogRunner(upload_file_engine, layout=KeyboardLayout(row_width=2, show_cancel=True))
