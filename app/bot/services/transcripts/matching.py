"""Какие пункты списка тем и вопросов, похоже, обсудили в выпуске.

Пункт считается обсуждённым, когда его значимые слова (в начальной форме)
встречаются в расшифровке рядом друг с другом: «Почему небо голубое?»
находится там, где в пределах одного окна звучат и «небо», и «голубой». Слова
по отдельности, разбросанные по часу разговора, совпадением не считаются.

Это подсказка, а не решение: ведущий подтверждает удаление кнопкой. Поэтому
правило простое и объяснимое, без моделей и внешних сервисов.

* у слов пункта веса: существительное важнее прилагательного и глагола;
* оценка пункта: доля веса его слов, найденных в лучшем окне расшифровки;
* совпадение по одному слову принимается, только если это слово звучит в
  выпуске несколько раз: «птица», мелькнувшая однажды, темой не была.
"""

from collections import Counter
from dataclasses import dataclass

from services.transcripts.lemmas import ADJECTIVE, NOUN, VERB, Lemma, lemmatize

# Сколько слов расшифровки подряд считается «рядом»: около минуты разговора.
WINDOW_WORDS = 150
THRESHOLD = 0.6
# Одно совпавшее слово должно прозвучать хотя бы столько раз.
MIN_REPEATS = 3

_WEIGHTS = {NOUN: 1.0, ADJECTIVE: 0.7, VERB: 0.6}


@dataclass(frozen=True)
class Match:
    item_id: int
    score: float
    words: tuple[str, ...]
    """Слова пункта, найденные в выпуске."""


def content_weights(text: str) -> dict[str, float]:
    """Значимые слова текста и их веса."""
    return {lemma.text: _WEIGHTS[lemma.kind] for lemma in lemmatize(text) if lemma.is_content}


def _best_window(positions: dict[str, list[int]], weights: dict[str, float], window: int) -> tuple[float, set[str]]:
    """Окно расшифровки, в котором собралось больше всего веса слов пункта.

    Окно скользит по упоминаниям слов пункта: каждое упоминание входит в него
    и выходит из него один раз.
    """
    hits = sorted((position, word) for word, places in positions.items() for position in places)
    inside: Counter[str] = Counter()
    weight = best_weight = 0.0
    best_words: set[str] = set()
    start = 0
    for position, word in hits:
        if not inside[word]:
            weight += weights[word]
        inside[word] += 1
        while position - hits[start][0] >= window:
            left = hits[start][1]
            inside[left] -= 1
            if not inside[left]:
                weight -= weights[left]
            start += 1
        if weight > best_weight + 1e-9:
            best_weight, best_words = weight, {found for found, count in inside.items() if count}
    return best_weight, best_words


def match_items(
    transcript: list[Lemma],
    items: list[tuple[int, str]],
    *,
    window: int = WINDOW_WORDS,
    threshold: float = THRESHOLD,
) -> list[Match]:
    """Пункты ``(id, текст)``, которые похожи на обсуждённые, в исходном порядке."""
    places: dict[str, list[int]] = {}
    for position, lemma in enumerate(transcript):
        if lemma.is_content:
            places.setdefault(lemma.text, []).append(position)

    matches = []
    for item_id, text in items:
        weights = content_weights(text)
        positions = {word: places[word] for word in weights if word in places}
        if not positions:
            continue
        weight, words = _best_window(positions, weights, window)
        score = weight / sum(weights.values())
        repeats = max(len(positions[word]) for word in words)
        if score >= threshold and (len(words) >= 2 or repeats >= MIN_REPEATS):
            matches.append(Match(item_id, round(score, 2), tuple(sorted(words))))
    return matches
