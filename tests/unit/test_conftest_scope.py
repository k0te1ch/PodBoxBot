"""Фикстуры из conftest.py остаются в своих каталогах.

У хендлеров и у тем есть по фикстуре ``fake_redis``: простая заглушка и
fakeredis. Пока rootdir pytest не совпадал с корнем репозитория, обе были
общими на весь прогон, и тесты получали ту, чей conftest загрузился
последним: ``pytest tests/unit/topics/test_form.py tests/unit/handlers/test_menus.py``
падал, хотя каждый файл по отдельности проходил.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPED = {
    "tests/unit/handlers": {"fake_redis", "publish_board_stub", "handler_factory"},
    "tests/unit/topics": {"fake_redis", "topics_on", "ticking_clock", "add_item"},
}


def test_rootdir_is_the_repository_root(request):
    assert request.config.rootpath.samefile(REPO_ROOT)


def test_directory_fixtures_are_not_global(request):
    manager = request.session._fixturemanager
    seen: dict[str, set[str]] = {}
    for name in {name for names in SCOPED.values() for name in names}:
        for definition in manager._arg2fixturedefs.get(name, []):
            seen.setdefault(definition.baseid, set()).add(name)

    # Каталог попадает сюда, только если его conftest.py загружен в этом прогоне.
    assert "" not in seen, f"fixtures visible to every test: {sorted(seen[''])}"
    for directory, names in seen.items():
        assert names <= SCOPED[directory]
