"""Текст списка и разбор «удали 1, 3»."""

import pytest

from services.i18n import t
from services.topics import Author, Item, Kind, Source, listing
from services.topics.listing import list_pages, parse_numbers, parse_removal


def _item(text: str, kind: Kind = Kind.TOPIC) -> Item:
    return Item(text=text, kind=kind, author=Author(name="@listener", user_id=7), source=Source.HASHTAG)


def test_list_looks_exactly_like_the_hosts_asked():
    items = [
        _item("Почему небо голубое?", Kind.QUESTION),
        _item("Почему птицы летают?", Kind.QUESTION),
        _item("Как съездили в отпуск"),
    ]

    [page] = list_pages(items)

    assert page.text == (
        "Список тем и вопросов:\n"
        "1) ВОПРОС - Почему небо голубое?\n"
        "2) ВОПРОС - Почему птицы летают?\n"
        "3) ТЕМА - Как съездили в отпуск"
    )
    assert page.numbers == [1, 2, 3]


def test_empty_list_says_so():
    [page] = list_pages([])

    assert page.text == t("topics_list_empty")
    assert page.numbers == []


def test_item_text_is_escaped_for_html():
    [page] = list_pages([_item("<b>жир</b> & co")])

    assert "&lt;b&gt;жир&lt;/b&gt; &amp; co" in page.text


def test_long_list_is_cut_into_messages_with_continuous_numbers(monkeypatch):
    monkeypatch.setattr(listing, "MAX_PAGE_CHARS", 120)
    items = [_item(f"тема номер {index} про что-нибудь важное") for index in range(1, 8)]

    pages = list_pages(items)

    assert len(pages) > 1
    assert pages[0].text.startswith("Список тем и вопросов:\n1) ТЕМА")
    assert all(len(page.text) <= 120 for page in pages)
    assert [number for page in pages for number in page.numbers] == list(range(1, 8))
    # Заголовок только в первом сообщении, продолжение начинается со своего номера.
    assert pages[1].text.startswith(f"{pages[1].numbers[0]}) ТЕМА")


def test_page_holds_no_more_items_than_buttons_fit(monkeypatch):
    monkeypatch.setattr(listing, "MAX_PAGE_ITEMS", 3)

    pages = list_pages([_item(f"тема {index}") for index in range(7)])

    assert [page.numbers for page in pages] == [[1, 2, 3], [4, 5, 6], [7]]


@pytest.mark.parametrize(
    ("text", "numbers"),
    [
        ("удали 1, 3, 4", [1, 3, 4]),
        ("Удали пункты 1, 3, 4", [1, 3, 4]),
        ("удали пункт 2", [2]),
        ("удалить 1 3 4.", [1, 3, 4]),
        ("убери 1 и 3", [1, 3]),
        ("удали 2-4, 7", [2, 3, 4, 7]),
        ("удали №5", [5]),
        ("удали: 3,3,1", [3, 1]),
        ("  вычеркни  10 ", [10]),
        ("delete 1, 2", [1, 2]),
    ],
)
def test_removal_requests_are_understood(text, numbers):
    assert parse_removal(text) == numbers


@pytest.mark.parametrize(
    "text",
    [
        "удали",
        "удали всё",
        "удали 1, 3 пожалуйста",
        "не удаляй 1",
        "удали 0",
        "удали 5-2",
        "удали 1-9999",
        "1, 3",
        "Number: 999",
        None,
    ],
)
def test_other_texts_are_not_removal_requests(text):
    assert parse_removal(text) is None


@pytest.mark.parametrize(
    ("args", "numbers"),
    [("1 3 4", [1, 3, 4]), ("1,3-5", [1, 3, 4, 5]), ("2 и 6", [2, 6]), ("", None), (None, None), ("все", None)],
)
def test_command_arguments(args, numbers):
    assert parse_numbers(args) == numbers
