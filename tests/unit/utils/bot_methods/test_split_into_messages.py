import pytest

from utils.bot_methods import split_into_messages


def _fits(messages: list[str], max_length: int) -> bool:
    return all(len(m.encode("utf-8")) <= max_length for m in messages)


def test_items_are_packed_until_the_limit():
    messages = split_into_messages("", "|", ["aaa", "bbb", "ccc"], max_length=10)

    assert messages == ["aaa|bbb", "ccc"]


def test_first_item_is_glued_to_a_non_empty_header():
    # Давнее поведение: разделитель ставится только между элементами, а между
    # header и первым элементом его нет. Единственный живой вызов передаёт
    # пустой header, так что стык не виден; тест фиксирует как есть.
    assert split_into_messages("H", "|", ["aaa"], max_length=10) == ["Haaa"]


def test_empty_items_produce_no_empty_message():
    assert split_into_messages("", "", [], max_length=10) == []


@pytest.mark.parametrize("max_length", [10, 32, 100])
def test_item_longer_than_the_limit_is_split(max_length):
    long_item = "x" * 250

    messages = split_into_messages("", "", [long_item], max_length)

    assert _fits(messages, max_length)
    assert "".join(messages) == long_item


def test_split_does_not_cut_a_multibyte_character_in_half():
    # «я» — два байта в UTF-8, поэтому нарезка по байтам без учёта границ
    # символов развалила бы строку на mojibake.
    long_item = "я" * 100

    messages = split_into_messages("", "", [long_item], max_length=15)

    assert _fits(messages, 15)
    assert "".join(messages) == long_item


def test_oversized_item_flushes_what_was_collected_before_it():
    messages = split_into_messages("", "|", ["short", "y" * 30], max_length=10)

    assert messages[0] == "short"
    assert _fits(messages, 10)
    assert "".join(messages[1:]) == "y" * 30
