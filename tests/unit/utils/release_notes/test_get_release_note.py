"""Тесты релиз-ноута: версия из CHANGELOG.md, текст из release-notes/ru.

`get_release_note` ищет CHANGELOG.md в cwd (кандидаты: ./CHANGELOG.md,
/app/CHANGELOG.md), а заметки рядом с ним в release-notes/ru/<версия>.md,
поэтому в тестах используем monkeypatch.chdir в tmp_path и кладём туда
фикстуры.
"""

import pytest

import utils.release_notes as release_notes
from utils.release_notes import get_release_note

# Реальный формат release-please: два релизных блока, английские секции,
# ссылки на PR/коммиты и **bold**-скоупы внутри пунктов.
_CHANGELOG = """\
# Changelog

## [0.4.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.3...v0.4.0) (2026-06-01)


### Features

* **boosty:** publish aftershow episodes ([#19](https://example.com/19)) ([e771c6f](https://example.com/c))


### Bug Fixes

* **compose:** default to direct connection ([#16](https://example.com/16))

## [0.3.3](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.2...v0.3.3) (2026-05-31)


### Features

* **boosty:** add Boosty publisher ([#14](https://example.com/14))
"""

_NOTES = """\
# 0.4.0

- Послешоу теперь выкладывается на Boosty.
- Бот подключается к площадкам напрямую, без <прокси> & лишних настроек.
Спасибо, что пользуетесь ботом!
"""


@pytest.fixture
def changelog_dir(tmp_path, monkeypatch):
    """Кладёт CHANGELOG.md в tmp_path и делает его текущей директорией."""
    (tmp_path / "CHANGELOG.md").write_text(_CHANGELOG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_notes(root, version: str, text: str) -> None:
    notes_dir = root / "release-notes" / "ru"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / f"{version}.md").write_text(text, encoding="utf-8")


@pytest.mark.asyncio
async def test_sends_russian_notes_for_latest_version(changelog_dir):
    _write_notes(changelog_dir, "0.4.0", _NOTES)
    _write_notes(changelog_dir, "0.3.3", "- Старый релиз.\n")

    parts = await get_release_note()

    assert parts == [
        "<b>Бот обновлён до версии 0.4.0</b>\n\nЧто изменилось:\n"
        "• Послешоу теперь выкладывается на Boosty.\n"
        "• Бот подключается к площадкам напрямую, без &lt;прокси&gt; &amp; лишних настроек.\n"
        "Спасибо, что пользуетесь ботом!"
    ]


@pytest.mark.asyncio
async def test_long_notes_are_split_into_tg_sized_parts(changelog_dir):
    bullets = "".join(f"- Пункт номер {i}: {'длинное описание ' * 10}\n" for i in range(40))
    _write_notes(changelog_dir, "0.4.0", bullets)

    parts = await get_release_note()

    assert len(parts) > 1
    for part in parts:
        assert part.startswith("<b>Бот обновлён до версии 0.4.0</b>")
        assert len(part.encode("utf-8")) <= release_notes._TG_MESSAGE_MAX_BYTES
    assert sum(part.count("• ") for part in parts) == 40


@pytest.mark.asyncio
async def test_missing_notes_send_version_only(changelog_dir):
    parts = await get_release_note()

    assert parts == ["Бот обновлён до версии 0.4.0."]
    # Английские строки CHANGELOG админам не уходят.
    assert "publish aftershow episodes" not in parts[0]


@pytest.mark.asyncio
async def test_missing_notes_are_logged(changelog_dir, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(release_notes.logger, "warning", warnings.append)

    await get_release_note()

    assert any("0.4.0.md" in message for message in warnings)


@pytest.mark.asyncio
async def test_empty_notes_send_version_only(changelog_dir):
    _write_notes(changelog_dir, "0.4.0", "# 0.4.0\n\n")

    assert await get_release_note() == ["Бот обновлён до версии 0.4.0."]


@pytest.mark.asyncio
async def test_missing_changelog_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # пустая директория, CHANGELOG.md нет
    assert await get_release_note() is None


@pytest.mark.asyncio
async def test_no_release_block_returns_none(tmp_path, monkeypatch):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nNothing here yet.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert await get_release_note() is None
