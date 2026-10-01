"""Сопоставление расшифровки со списком тем и ключевые слова, на подготовленных текстах.

``episode_reference.txt``: текст выпуска, написанный для теста. В нём обсуждают
отпуск, почему небо голубое и кофе, а птица, книги и микрофон упоминаются
мимоходом. ``episode_whisper_small.txt``: то, что faster-whisper (модель
``small``, CPU, int8) расслышал в первых десяти минутах этого же текста,
начитанного синтезатором: с настоящими ошибками распознавания.
"""

from pathlib import Path

import pytest

from services.transcripts.keywords import as_hashtags, suggest_keywords
from services.transcripts.lemmas import lemmatize
from services.transcripts.matching import content_weights, match_items

FIXTURES = Path(__file__).parent / "fixtures"

SKY, BIRDS, HOLIDAY, AI, COFFEE = 1, 2, 3, 4, 5
ITEMS = [
    (SKY, "Почему небо голубое?"),
    (BIRDS, "Почему птицы летают?"),
    (HOLIDAY, "Как съездили в отпуск"),
    (AI, "Расскажите про искусственный интеллект"),
    (COFFEE, "Кофе в турке или растворимый?"),
]


@pytest.fixture(scope="module", params=["episode_reference.txt", "episode_whisper_small.txt"])
def episode(request):
    return lemmatize((FIXTURES / request.param).read_text(encoding="utf-8"))


def _ids(matches) -> list[int]:
    return [match.item_id for match in matches]


def test_discussed_items_are_found_and_the_rest_are_not(episode):
    matches = match_items(episode, ITEMS)

    assert _ids(matches) == [SKY, HOLIDAY, COFFEE]
    assert all(match.score >= 0.6 for match in matches)


def test_match_says_which_words_were_heard(episode):
    by_id = {match.item_id: match for match in match_items(episode, ITEMS)}

    assert by_id[SKY].words == ("голубой", "небо")
    assert "отпуск" in by_id[HOLIDAY].words


def test_word_forms_do_not_matter():
    transcript = lemmatize("В этом году мы говорили об отпусках. Отпуском все довольны, в отпуске было хорошо.")

    assert _ids(match_items(transcript, [(1, "Отпуск")])) == [1]
    assert content_weights("Как съездили в отпуск") == {"съездить": 0.6, "отпуск": 1.0}


def test_words_far_apart_are_not_a_discussion():
    filler = "Потом мы долго обсуждали ремонт на кухне и новую плитку. " * 40
    scattered = lemmatize("Сегодня ясное небо. " + filler + "А ещё у меня голубой чайник.")
    together = lemmatize(filler + "Кстати, почему небо голубое, знаешь?")

    assert match_items(scattered, [(1, "Почему небо голубое?")]) == []
    assert _ids(match_items(together, [(1, "Почему небо голубое?")])) == [1]


def test_one_passing_mention_is_not_enough():
    once = lemmatize("У меня за окном села птица и смотрит на меня.")
    often = lemmatize("Птица села на окно. Эта птица прилетает каждый день. Я кормлю птицу хлебом.")

    assert match_items(once, [(1, "Почему птицы летают?")]) == []
    assert _ids(match_items(often, [(1, "Почему птицы летают?")])) == [1]


def test_items_without_meaningful_words_never_match(episode):
    assert match_items(episode, [(1, "А что это?"), (2, "Как вы?"), (3, "...")]) == []


def test_empty_transcript_and_empty_list():
    assert match_items([], ITEMS) == []
    assert match_items(lemmatize("про отпуск и небо"), []) == []


def test_passing_mentions_close_together_look_like_a_discussion(episode):
    """Известный предел подхода: «за отпуск прочитал книгу» похоже на разговор
    о книгах. Поэтому бот только предлагает, а удаляет ведущий."""
    books = [(1, "Какие книги читаете и что посоветуете")]

    [match] = match_items(episode, books)

    assert match.words == ("книга", "читать")


def test_window_and_threshold_are_adjustable():
    transcript = lemmatize("небо сегодня затянуто серыми тучами, зато чайник у меня голубой")
    item = [(1, "Почему небо голубое и высокое")]

    assert _ids(match_items(transcript, item, window=20)) == [1]
    assert match_items(transcript, item, window=3) == []
    # Найдены два слова из трёх: доля веса 1,7 из 2,4.
    assert match_items(transcript, item, window=20, threshold=0.8) == []


def test_keywords_are_frequent_nouns_of_the_episode(episode):
    keywords = suggest_keywords(episode)

    assert {"небо", "отпуск", "свет"} <= set(keywords)
    assert len(keywords) <= 10
    # Служебные и разговорные слова в хештеги не идут.
    assert not {"привет", "человек", "вопрос", "выпуск", "время", "спасибо"} & set(keywords)


def test_keywords_need_repetition_and_respect_the_limit():
    transcript = lemmatize("море море море горы горы горы лес лес лес река озеро")

    assert suggest_keywords(transcript) == ["гора", "море"]
    assert suggest_keywords(transcript, limit=1) == ["гора"]
    assert suggest_keywords(lemmatize("один раз сказанное слово")) == []


def test_names_and_places_rank_higher_at_equal_counts():
    transcript = lemmatize("Москва чайник Москва чайник Москва чайник")

    assert suggest_keywords(transcript)[0] == "москва"


def test_hashtags_are_built_from_keywords():
    assert as_hashtags(["отпуск", "санкт-петербург"]) == "#отпуск #санкт_петербург"
    assert as_hashtags([]) == ""


def test_latin_names_are_matched_and_suggested():
    transcript = lemmatize(
        "Сегодня про ChatGPT. Я спросил у ChatGPT рецепт супа, и ChatGPT ответил. "
        "А потом ChatGPT написал мне скрипт на Python."
    )

    assert _ids(match_items(transcript, [(1, "Что думаете про ChatGPT и Python?")])) == [1]
    assert suggest_keywords(transcript) == ["chatgpt"]


def test_dense_transcript_is_matched_in_one_pass():
    """Слово пункта звучит тысячи раз: окно не пересчитывается заново на каждом упоминании."""
    transcript = lemmatize("небо голубой отпуск " * 20_000)
    items = [(index, "Почему небо голубое?") for index in range(50)]

    assert len(match_items(transcript, items)) == 50


def test_best_window_counts_each_word_once():
    transcript = lemmatize("небо небо небо небо и больше ничего про цвет")

    [match] = match_items(transcript, [(1, "Небо")])

    assert (match.score, match.words) == (1.0, ("небо",))
    assert match_items(transcript, [(1, "Почему небо голубое и высокое")]) == []
