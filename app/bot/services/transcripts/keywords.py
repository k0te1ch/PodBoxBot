"""Ключевые слова выпуска: из чего ведущим собрать хештеги.

Берутся существительные в начальной форме, которые в выпуске звучат чаще
других, без служебных и «разговорных» слов. Имена, названия и география
получают небольшую надбавку: по ним выпуск ищут охотнее. Это частотная
подсказка, а не тематический анализ: итоговые хештеги выбирает человек.
"""

from collections import Counter

from services.transcripts.lemmas import NOUN, Lemma

DEFAULT_LIMIT = 10
MIN_LENGTH = 4
# Слово, сказанное в выпуске один-два раза, темой не было.
MIN_COUNT = 3
PROPER_BONUS = 1.5


def suggest_keywords(transcript: list[Lemma], limit: int = DEFAULT_LIMIT) -> list[str]:
    """Самые частые существительные выпуска, от частых к редким."""
    counts: Counter[str] = Counter()
    proper: set[str] = set()
    for lemma in transcript:
        if lemma.kind == NOUN and lemma.is_content and len(lemma.text) >= MIN_LENGTH:
            counts[lemma.text] += 1
            if lemma.proper:
                proper.add(lemma.text)

    def score(word: str) -> float:
        return counts[word] * (PROPER_BONUS if word in proper else 1.0)

    frequent = [word for word, count in counts.items() if count >= MIN_COUNT]
    return sorted(frequent, key=lambda word: (-score(word), word))[:limit]


def as_hashtags(words: list[str]) -> str:
    """«отпуск», «солнечный-свет» → «#отпуск #солнечный_свет»."""
    return " ".join("#" + word.replace("-", "_") for word in words)
