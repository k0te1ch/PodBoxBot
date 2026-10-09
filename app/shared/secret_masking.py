"""Секреты из настроек для маскировки sagenza-tgbot-sdk, включая короткие.

SDK вырезает известные секреты точным совпадением, но значения короче
``MIN_SECRET_LENGTH`` не регистрирует: иначе из логов пропало бы каждое «42».
Пароль FTP бывает и таким. Короткое значение здесь маскируется не везде, а
только там, где это точно секрет:

* после имени ключа: ``FTP_PASSWORD 1234``, ``password is '1234'``,
  ``PASS 1234``, «пароль: 1234»;
* в адресе: ``ftp://user:1234@host`` и ``user:1234@host`` без схемы;
* рядом с известным логином: ``podcast/1234``, ``podcast:1234``.

Общий слой SDK не меняется: шаблоны добавляются через его же
``register_patterns``, порог длины остаётся прежним.

Зависит только от stdlib и от модуля ``masking`` SDK, поэтому годится и боту,
и публишерам (у них SDK стоит без aiogram).
"""

import re
from collections.abc import Iterable, Mapping

from sagenza_tgbot_sdk.masking import MIN_SECRET_LENGTH, register_patterns, register_secrets

# Слова, после которых короткое значение считается секретом.
_KEY_WORDS = r"pass(?:word|wd|phrase)?|pwd|пароль\w*|secret|token|api[_-]?key|auth|credentials?"

# Что может стоять между ключом и значением: пробел, «=», «:», кавычки, скобки.
_GAP = r"""(?:\s+is)?[\s=:'"(\[{<-]{1,4}"""

# Разделитель между логином и паролем в паре.
_PAIR = r"""\s*[:/,;|]\s*['"]?"""


def short_secret_patterns(name: str, value: str, logins: Iterable[str | None] = ()) -> list[str]:
    """Шаблоны, которые вырезают короткий секрет ``value`` по ключу и по месту.

    В каждом шаблоне маскируется только группа ``secret``: ключ, логин и адрес
    остаются в тексте. Регистр ключа не важен, само значение сравнивается точно.
    """
    secret = rf"(?P<secret>{re.escape(value)})(?!\w)"
    patterns = [
        rf"(?i:{re.escape(name)}|{_KEY_WORDS}){_GAP}{secret}",
        rf"(?<=:)(?P<secret>{re.escape(value)})(?=@)",
    ]
    patterns.extend(rf"(?<!\w){re.escape(login)}{_PAIR}{secret}" for login in logins if login and login.strip())
    return patterns


def register_named_secrets(values: Mapping[str, str | None], logins: Iterable[str | None] = ()) -> None:
    """Отдаёт маскировке секреты ``{имя настройки: значение}``.

    Длинные значения вырезаются точным совпадением, как и раньше. Короткие,
    которые SDK пропускает, вырезаются по ключу и по месту. ``logins``:
    логины, рядом с которыми может оказаться пароль.
    """
    logins = [login for login in logins if login]
    for name, value in values.items():
        if value is None or not value.strip():
            continue
        if len(value.strip()) >= MIN_SECRET_LENGTH:
            register_secrets(value)
        else:
            register_patterns(*short_secret_patterns(name, value, logins))
