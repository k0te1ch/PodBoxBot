"""Слова текста в начальной форме: «в отпуске» и «про отпуск» — одно слово.

Лемматизация идёт через pymorphy3 (словарь OpenCorpora), без сети и внешних
сервисов. Библиотека подгружается при первом вызове: без включённой
расшифровки бот её не трогает.

Словарь не знает контекста. Редкое имя может получить чужую начальную форму
(«Илон» станет «илона»): для сопоставления это не страшно, обе стороны
приводятся одинаково, а в ключевых словах такое слово поправит человек.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

_WORD = re.compile(r"[а-яёa-z]+(?:-[а-яёa-z]+)*", re.IGNORECASE)

NOUN = "noun"
ADJECTIVE = "adjective"
VERB = "verb"
OTHER = "other"

_KINDS = {
    "NOUN": NOUN,
    "ADJF": ADJECTIVE,
    "ADJS": ADJECTIVE,
    "PRTF": VERB,
    "PRTS": VERB,
    "VERB": VERB,
    "INFN": VERB,
    "GRND": VERB,
}
# Имена, фамилии, география, организации: в ключевые слова такие идут охотнее.
_PROPER = ("Name", "Surn", "Patr", "Geox", "Orgn", "Trad")

# Слова, которые есть в любом разговоре и ни о чём не говорят: по ним нельзя
# ни сопоставить пункт списка с выпуском, ни предложить хештег.
STOPWORDS = frozenset(
    [
        "быть",
        "стать",
        "мочь",
        "хотеть",
        "сказать",
        "говорить",
        "знать",
        "думать",
        "делать",
        "сделать",
        "идти",
        "пойти",
        "дать",
        "давать",
        "взять",
        "брать",
        "видеть",
        "смотреть",
        "понять",
        "понимать",
        "получаться",
        "получиться",
        "казаться",
        "оказаться",
        "начать",
        "начинать",
        "стоять",
        "сидеть",
        "иметь",
        "спрашивать",
        "спросить",
        "рассказать",
        "рассказывать",
        "человек",
        "люди",
        "время",
        "год",
        "день",
        "раз",
        "дело",
        "вещь",
        "штука",
        "вопрос",
        "тема",
        "выпуск",
        "подкаст",
        "слушатель",
        "часть",
        "место",
        "случай",
        "сторона",
        "образ",
        "конец",
        "начало",
        "вид",
        "слово",
        "история",
        "минута",
        "час",
        "неделя",
        "привет",
        "спасибо",
        "пока",
        "пожалуйста",
        "ладно",
        "письмо",
        "чат",
        "такой",
        "какой",
        "который",
        "этот",
        "тот",
        "весь",
        "сам",
        "свой",
        "наш",
        "ваш",
        "мой",
        "твой",
        "один",
        "другой",
        "каждый",
        "самый",
        "любой",
        "некоторый",
        "новый",
        "хороший",
        "большой",
        "маленький",
        "первый",
        "второй",
        "последний",
        "следующий",
        "целый",
        "разный",
        "нужный",
        "общий",
        "главный",
    ]
)


@dataclass(frozen=True)
class Lemma:
    text: str
    kind: str
    proper: bool = False

    @property
    def is_content(self) -> bool:
        """Слово со смыслом: существительное, прилагательное или глагол не из стоп-списка."""
        return self.kind != OTHER and self.text not in STOPWORDS and len(self.text) > 2


@lru_cache(maxsize=1)
def _analyzer() -> Any:
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=50_000)
def lemma_of(word: str) -> Lemma:
    if word.isascii():
        # Латиницу словарь не знает: «Python», «ChatGPT» считаем названиями.
        return Lemma(text=word, kind=NOUN, proper=True)
    parsed = _analyzer().parse(word)[0]
    tag = parsed.tag
    return Lemma(
        text=parsed.normal_form.replace("ё", "е"),
        kind=_KINDS.get(str(tag.POS), OTHER),
        proper=any(mark in tag for mark in _PROPER),
    )


def lemmatize(text: str) -> list[Lemma]:
    """Все слова текста по порядку, в начальной форме."""
    return [lemma_of(word.lower()) for word in _WORD.findall(text or "")]
