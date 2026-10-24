"""Пост на сайт из шаблона без Tags и Chapters."""

import pytz
from app.publishers.WordPress.wordpress import WordPress


def _wp() -> WordPress:
    wp = WordPress.__new__(WordPress)
    wp._timezone = pytz.timezone("Europe/Moscow")
    wp._wp_url = "https://example.com"
    return wp


def test_post_without_chapters_has_no_empty_timeline(sample_post_info):
    info = {**sample_post_info, "chapters": [], "tags": []}

    form = _wp()._build_form(info)

    assert "Таймлайн" not in form["content"]
    assert "<!--more-->\n\nВсё это вы услышите в 123-м эпизоде" in form["content"]
    assert form["tax_input[post_tag]"] == ""


def test_post_with_chapters_keeps_the_timeline(sample_post_info):
    form = _wp()._build_form(sample_post_info)

    assert "<!--more--><b><i>Таймлайн:</i></b>\n[skipto time=00:00:00]" in form["content"]
    assert "[skipto time=00:10:00]00:10:00[/skipto] — Середина\n\nВсё это" in form["content"]


def test_post_heading_is_large_and_bold(sample_post_info):
    content = _wp()._build_form(sample_post_info)["content"]

    assert content.startswith('<span style="font-size: x-large;"><strong>')
    assert "</strong></span>\n\n<b><i>Описание:</i></b>\n" in content


def test_post_blocks_are_separated_by_blank_lines(sample_post_info):
    content = _wp()._build_form(sample_post_info)["content"]

    assert "\n\n<!--more--><b><i>Таймлайн:</i></b>\n" in content
    assert "[/skipto] — Середина\n\nВсё это" in content
    assert "подкаста «Разговорный жанр».\n\n[podlove-template" in content
    assert '"subscriptions"]\n\n<span style="font-size: small;">Дата записи:' in content
    assert "\n\n\n" not in content
