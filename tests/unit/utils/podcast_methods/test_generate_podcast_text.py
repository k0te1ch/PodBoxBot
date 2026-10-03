from unittest.mock import patch

import pytest

from utils.podcast_methods import generate_podcast_text


@pytest.fixture
def podcast_info():
    """Фикстура с данными для тестирования."""
    return {
        "number": "42",
        "title": "Название эпизода",
        "comment": "Это описание эпизода.",
        "chapters": [
            ["00:00:07", "Вступление"],
            ["00:10:20", "Основная часть"],
            ["00:40:15", "Заключение"],
        ],
        "support_link": "https://support.link",
    }


@patch("utils.podcast_methods.SUPPORT_LINK", "https://support.link")
def test_generate_podcast_text(podcast_info):
    """Тестирует генерацию текста для подкаста."""
    expected_output = (
        "<b>Название эпизода</b>\n\n"
        "<i>Описание:</i>\n"
        "Это описание эпизода.\n\n"
        "<i>Таймлайн:</i>\n"
        "00:00:07 — Вступление\n"
        "00:10:20 — Основная часть\n"
        "00:40:15 — Заключение\n\n"
        "Всё это вы услышите в 42-м эпизоде подкаста «Разговорный жанр».\n\n"
        '<i><b><a href="https://support.link">🍩 Поддержать подкаст</a></b></i>'
    )

    result = generate_podcast_text(podcast_info)
    assert result == expected_output


@patch("utils.podcast_methods.SUPPORT_LINK", "https://support.link")
@pytest.mark.parametrize("chapters", [None, []], ids=["no chapters key", "empty chapters"])
def test_text_without_chapters_has_no_timeline(podcast_info, chapters):
    # A template without Chapters is valid: the post is built without the timeline block.
    del podcast_info["chapters"]
    if chapters is not None:
        podcast_info["chapters"] = chapters

    assert generate_podcast_text(podcast_info) == (
        "<b>Название эпизода</b>\n\n"
        "<i>Описание:</i>\n"
        "Это описание эпизода.\n\n"
        "Всё это вы услышите в 42-м эпизоде подкаста «Разговорный жанр».\n\n"
        '<i><b><a href="https://support.link">🍩 Поддержать подкаст</a></b></i>'
    )


def test_markup_characters_in_the_episode_text_are_escaped(podcast_info):
    # The post is sent as HTML: a bare "<" in a title typed by a host or taken
    # from the RSS feed made Telegram reject the whole message.
    podcast_info |= {
        "title": "5 < 6 & <b>co</b>",
        "comment": "Гость сказал: a < b && c > d",
        "chapters": [["00:00:07", "Вопрос <слушателя>"]],
        "support_link": "https://support.link/?a=1&b=2",
    }

    text = generate_podcast_text(podcast_info)

    assert "<b>5 &lt; 6 &amp; &lt;b&gt;co&lt;/b&gt;</b>" in text
    assert "Гость сказал: a &lt; b &amp;&amp; c &gt; d" in text
    assert "00:00:07 — Вопрос &lt;слушателя&gt;" in text
    assert '<a href="https://support.link/?a=1&amp;b=2">' in text


def test_escaped_post_is_valid_telegram_html(podcast_info):
    """Разметка поста после экранирования разбирается так же, как её разберёт Telegram:
    теги только свои, парные."""
    from html.parser import HTMLParser

    podcast_info["title"] = "</b><i>unclosed"

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.seen = [], []

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)
            self.seen.append(tag)

        def handle_endtag(self, tag):
            assert self.stack.pop() == tag

    parser = Tags()
    parser.feed(generate_podcast_text(podcast_info))

    assert parser.stack == []
    assert set(parser.seen) == {"b", "i", "a"}
