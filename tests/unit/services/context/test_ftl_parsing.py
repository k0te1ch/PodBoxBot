"""Разбор .ftl в services/context.py."""

from services.context import _parse_ftl_file


def test_escaped_newline_in_single_line_value(tmp_path):
    ftl = tmp_path / "ru.ftl"
    ftl.write_text("done_tag = Теги проставлены.\\nЗагрузка началась\n", encoding="utf-8")

    assert _parse_ftl_file(ftl)["done_tag"] == "Теги проставлены.\nЗагрузка началась"


def test_real_locales_have_no_literal_escapes():
    from services.context import LOCALES_DIR

    for locale in LOCALES_DIR.glob("*.ftl"):
        for key, value in _parse_ftl_file(locale).items():
            if isinstance(value, str):
                assert "\\n" not in value, f"{locale.name}:{key}"
