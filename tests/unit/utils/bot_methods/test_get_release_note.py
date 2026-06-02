"""Тесты парсера release-note под формат release-please.

`get_release_note` читает CHANGELOG.md из cwd (кандидаты: ./CHANGELOG.md,
/app/CHANGELOG.md), поэтому в тестах используем monkeypatch.chdir в tmp_path
и кладём туда фикстуру changelog.
"""

import pytest

from utils.bot_methods import get_release_note

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


@pytest.fixture
def changelog_dir(tmp_path, monkeypatch):
    """Кладёт CHANGELOG.md в tmp_path и делает его текущей директорией."""
    (tmp_path / "CHANGELOG.md").write_text(_CHANGELOG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_parses_latest_block_only(changelog_dir):
    parts = await get_release_note()

    assert parts is not None
    header = parts[0]
    # Версия и ISO-дата из верхнего блока.
    assert "версия 0.4.0" in header
    assert "от 2026-06-01" in header
    # Версия из старого блока не должна протечь.
    joined = "\n".join(parts)
    assert "0.3.3" not in joined
    assert "add Boosty publisher" not in joined


@pytest.mark.asyncio
async def test_sections_mapped_and_bullets_cleaned(changelog_dir):
    parts = await get_release_note()
    joined = "\n".join(parts)

    # Английские заголовки секций → русские подписи.
    assert "<i>Добавлено</i>:" in joined
    assert "<i>Исправлено</i>:" in joined
    # Пункт: ссылки свёрнуты в текст, **bold** убран, есть буллет.
    assert "• boosty: publish aftershow episodes" in joined
    assert "(#19)" in joined  # markdown-ссылка [#19](url) → #19
    assert "https://example.com" not in joined  # url-шум вычищен
    assert "**" not in joined


@pytest.mark.asyncio
async def test_missing_changelog_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # пустая директория, CHANGELOG.md нет
    assert await get_release_note() is None


@pytest.mark.asyncio
async def test_no_release_block_returns_none(tmp_path, monkeypatch):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nNothing here yet.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert await get_release_note() is None
