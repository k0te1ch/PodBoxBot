# Changelog

## [0.3.2](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.1...v0.3.2) (2026-05-30)


### Bug Fixes

* **bot:** report all handler errors to DEVELOPER reliably ([#12](https://github.com/k0te1ch/PodBoxBot/issues/12)) ([65d3305](https://github.com/k0te1ch/PodBoxBot/commit/65d3305914453867682f3e29b0de881b70f31792))

## [0.3.1](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.0...v0.3.1) (2026-05-30)


### Bug Fixes

* **bot:** regenerate poetry.lock after adding tgtest dep ([8d70e86](https://github.com/k0te1ch/PodBoxBot/commit/8d70e869ef0b23e6c1498310bb9edf8a6b773a87))
* **bot:** render release-note in HTML, split by section, skip empty header ([c4a4043](https://github.com/k0te1ch/PodBoxBot/commit/c4a4043939bd9f7108283c7e0d19d67525e023ef))

## 0.3.0 (28.05.2026)

## Добавлено

- WordPress publisher теперь использует Podlove REST API (Application Password) для заполнения метаданных эпизода и chapters — title/summary/number/slug/duration/chapters наконец-то долетают до плеера
- Авто-решение JS-only bot-protection challenge (cookie `bpc`) на WP-сайтах за WAF — сессия больше не зацикливается на странице-перехватчике
- Persistence шаблона эпизода в sidecar-JSON рядом с MP3 — кнопки «FTP», «Сайт», «Переслать в чат» снова работают (Telegram не присылает `reply_to_message` в callback-апдейтах для audio)
- `utils/bootstrap.sh` — первичный деплой на чистый prod-сервер: backup volumes, поэтапный up с health-ожиданием, верификация Kafka-топиков и Avro-схем, smoke pub/sub
- `docker-compose.direct.yml` — режим без tun2socks для хостов с прямым доступом к Telegram DC
- Полноценный README с описанием проекта, потока данных и деплой-инструкцией
- e2e-тест на базе tgtest для прогона полной цепочки публикации против живого бота
- Обязательный новый ключ конфигурации `WP_APP_PASSWORD` (Application Password из WP Admin → Users → Profile)

## Улучшено

- `shared/config` лишился легаси-обёртки `SharedSettings.get()` — все потребители теперь используют атрибутный доступ; добавлены явные поля `RESULT_TOPIC` / `WP_RESULT_TOPIC` / `WP_APP_PASSWORD`
- Клавиатуры (`admin.py`, `podcast_handler.py`) свелись к единому стилю `ru/en` namespaces — без кэш-словарей и дублирующихся геттеров
- `redis`-синглтон ре-экспортируется из `services/redis.py` вместо in-place реассайна — `from services import redis` теперь возвращает один и тот же объект во всех импортёрах
- WordPress publisher оборачивает все HTTP-вызовы form-флоу в timeout + exponential backoff retry; в логах появилось содержимое тел ответов при ошибках
- Bot Dockerfile теперь строится только до stage `final` — больше не натыкаемся на `poetry install --with dev` и сломанный poetry↔dulwich
- Schema Registry health-чек переехал на `cub sr-ready` с `start_period: 60s` — не флапает на медленном холодном старте
- `REDIS_URL` собирается в `bot/config.py` из `REDIS_PASSWORD` с URL-encoding пароля — спецсимволы (`@`, `:`, `/`, и т.п.) больше не ломают подключение
- `docker-compose.yml` дополнительно прокидывает `TELEGRAM_VERBOSITY=3` для telegram-bot-api

## Исправлено

- WordPress `_login` переписан под WP 6.x: `allow_redirects=False`, проверка 302+`wordpress_logged_in_*`, парсинг `<div id="login_error">` для диагностики; убрана сломанная heuristic `document.location.href="http://...wp-admin"`
- `_check_session` больше не скрапит HTML, а проверяет статус-код через `/wp-admin/` с `allow_redirects=False`
- `i18n`: многострочные FTL-значения в объектах больше не поглощают следующий атрибут с `.key = ...`
- `i18n`: `_LangWrapper.__getitem__` корректно поднимается по фреймам — `context[lang].section.field` теперь видит реальные locals вызывающего вместо обёртки
- Анимация точек в `monitor_file_progress` идёт через `itertools.cycle` вместо одноразового `iter` — больше не замирает после 4 тиков
- `on_startup` бота изолирует падение `send_release_note` так, чтобы регистрация Kafka-консьюмеров (FTP/WordPress result-топики) всё равно выполнялась — устранена «kafka работает в одну сторону»
- Отсутствие `CHANGELOG.md` больше не валит запуск бота — `get_release_note` возвращает `None` с warning'ом
- При провале загрузки MP3 в `get_MP3` бот теперь пишет в чат «MP3 не загружен» вместо тихого ожидания шаблона; `check_exists_file_by_size` возвращает `None` вместо `NotADirectoryError`
- `check_version` корректно реагирует на не-настроенный Redis — бот работает с `MemoryStorage` без CRITICAL-логов
