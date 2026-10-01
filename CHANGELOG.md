# Changelog

## [0.9.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.8.0...v0.9.0) (2026-10-01)


### Features

* **boosty:** add draft and scheduled publish modes ([#97](https://github.com/k0te1ch/PodBoxBot/issues/97)) ([8dac205](https://github.com/k0te1ch/PodBoxBot/commit/8dac20543aadc3b9bf0f70c1595d36863a561047))
* **bot:** send admins russian release notes instead of the changelog ([#99](https://github.com/k0te1ch/PodBoxBot/issues/99)) ([3b4185e](https://github.com/k0te1ch/PodBoxBot/commit/3b4185e96a371f5fd787f4698c6d8ca22c5195f1))
* **bot:** use sdk logging and add optional metrics forwarding ([#90](https://github.com/k0te1ch/PodBoxBot/issues/90)) ([544948d](https://github.com/k0te1ch/PodBoxBot/commit/544948d8feef4c03b2165571a3a57ec82388b4bd))
* **metrics:** add business metrics for the bot and publishers ([#113](https://github.com/k0te1ch/PodBoxBot/issues/113)) ([0a25a0a](https://github.com/k0te1ch/PodBoxBot/commit/0a25a0a6e8eb004e3f581b8ec6546c6061684223))
* **monitoring:** russian dashboards and a podcast publications board ([#115](https://github.com/k0te1ch/PodBoxBot/issues/115)) ([095ef0f](https://github.com/k0te1ch/PodBoxBot/commit/095ef0fbc2210d577faa49dc7fc532deda2af27d))


### Bug Fixes

* **bot:** describe what each platform did in the publish status ([#94](https://github.com/k0te1ch/PodBoxBot/issues/94)) ([536c924](https://github.com/k0te1ch/PodBoxBot/commit/536c924e9e44ba4467726e1768b637595c50c614))
* **bot:** publish templates without chapters to the site ([#93](https://github.com/k0te1ch/PodBoxBot/issues/93)) ([4478e1e](https://github.com/k0te1ch/PodBoxBot/commit/4478e1ef24f9e3260f32a67431232e798328619b))
* **bot:** report ftp errors when looking up the episode number ([#92](https://github.com/k0te1ch/PodBoxBot/issues/92)) ([74653d1](https://github.com/k0te1ch/PodBoxBot/commit/74653d160fbd053264684924be1d532d0a9aebf0))
* **ci:** read the release branch sha before dispatching its checks ([#110](https://github.com/k0te1ch/PodBoxBot/issues/110)) ([9474c07](https://github.com/k0te1ch/PodBoxBot/commit/9474c07f2c7e0394c39fb0bac332a4347c08084d))
* **monitoring:** let grafana start on volumes with old datasources ([#107](https://github.com/k0te1ch/PodBoxBot/issues/107)) ([0475fb1](https://github.com/k0te1ch/PodBoxBot/commit/0475fb1383db12d4ea5e563878e4a114f712ada6))
* **monitoring:** scrape redis exporter by its compose service name ([#96](https://github.com/k0te1ch/PodBoxBot/issues/96)) ([a411bc7](https://github.com/k0te1ch/PodBoxBot/commit/a411bc7284252d8ad0aba0b8b3a600f6f5eb5a83))
* **publishers:** treat empty settings as unset ([#95](https://github.com/k0te1ch/PodBoxBot/issues/95)) ([a184d74](https://github.com/k0te1ch/PodBoxBot/commit/a184d743b17d57a4021711f54ca81ce751325c20))

## [0.8.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.7.0...v0.8.0) (2026-09-27)


### Features

* **boosty:** refresh tokens reliably and explain auth failures ([#83](https://github.com/k0te1ch/PodBoxBot/issues/83)) ([e0d234f](https://github.com/k0te1ch/PodBoxBot/commit/e0d234f0c61e5a05e1a43455614f932b96497124))
* **bot:** collect host notes and listener questions by hashtag ([#80](https://github.com/k0te1ch/PodBoxBot/issues/80)) ([9183396](https://github.com/k0te1ch/PodBoxBot/commit/9183396b0721572667d7a2574c4d74585acc1fd1))
* **bot:** rss episode notifications and service messages ([#79](https://github.com/k0te1ch/PodBoxBot/issues/79)) ([19750f8](https://github.com/k0te1ch/PodBoxBot/commit/19750f83ac485ea952893c43b30bb099082f11b8)), closes [#474](https://github.com/k0te1ch/PodBoxBot/issues/474)
* **monitoring:** extend grafana dashboard and add alert rules ([#82](https://github.com/k0te1ch/PodBoxBot/issues/82)) ([13dea32](https://github.com/k0te1ch/PodBoxBot/commit/13dea3258abac41670d2450f16b3a18c99424395))
* **monitoring:** send grafana alerts to telegram and skip other shows in rss ([#86](https://github.com/k0te1ch/PodBoxBot/issues/86)) ([67cd830](https://github.com/k0te1ch/PodBoxBot/commit/67cd830a1c346da2ed5a641f38145cfc2b3284d3))
* **publishers:** publish aftershows to VK Donut, Patreon and Sponsr ([#84](https://github.com/k0te1ch/PodBoxBot/issues/84)) ([ed2541c](https://github.com/k0te1ch/PodBoxBot/commit/ed2541cb36e68a9e34006a9651a1a0277f72649b))


### Bug Fixes

* **bot:** report every publishing step and check forwarded posts ([#81](https://github.com/k0te1ch/PodBoxBot/issues/81)) ([2756764](https://github.com/k0te1ch/PodBoxBot/commit/275676499913d7e67262f1c276b03355e8d42ed9))
* **wordpress:** make draft publishing idempotent and verify the right endpoint ([#78](https://github.com/k0te1ch/PodBoxBot/issues/78)) ([625f68e](https://github.com/k0te1ch/PodBoxBot/commit/625f68ee3c1c5611182215e007d6955686d1d3f0))

## [0.7.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.6.0...v0.7.0) (2026-09-27)


### Features

* **bot:** run dialogs on DialogEngine 0.3 and menus on the SDK ([#73](https://github.com/k0te1ch/PodBoxBot/issues/73)) ([97e258f](https://github.com/k0te1ch/PodBoxBot/commit/97e258fcfd9bc2843cd6c9e53f2beb485b01336e))
* **publishers:** retry external calls and verify published posts ([#72](https://github.com/k0te1ch/PodBoxBot/issues/72)) ([4736563](https://github.com/k0te1ch/PodBoxBot/commit/4736563318abb22222958befc7c44ad67bcaf740))

## [0.6.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.5.1...v0.6.0) (2026-09-27)


### Features

* **bot:** connect sagenza-tgbot-sdk for metrics, health and /status ([#71](https://github.com/k0te1ch/PodBoxBot/issues/71)) ([ae5b6af](https://github.com/k0te1ch/PodBoxBot/commit/ae5b6af8ae2dbc21450870a7f1fd6aeb7dfdcb88))
* **bot:** drive episode upload dialog via dialog-engine ([#29](https://github.com/k0te1ch/PodBoxBot/issues/29)) ([d1d11cf](https://github.com/k0te1ch/PodBoxBot/commit/d1d11cf5915be22534c9a66933b875fe55ae9858))
* **wordpress:** fix podcast draft fields and add recording date ([#36](https://github.com/k0te1ch/PodBoxBot/issues/36)) ([01bcdd4](https://github.com/k0te1ch/PodBoxBot/commit/01bcdd428155fb10180b4dfefb83c6a1f8410c41))


### Bug Fixes

* **boosty:** cancel hourly refresh task when publisher stops ([#37](https://github.com/k0te1ch/PodBoxBot/issues/37)) ([3a7671c](https://github.com/k0te1ch/PodBoxBot/commit/3a7671cc39dcc8635babe2cb3f0031f8a4463a30))
* **bot:** literal \n in messages and string-sorted episode numbers ([#46](https://github.com/k0te1ch/PodBoxBot/issues/46)) ([89ac26f](https://github.com/k0te1ch/PodBoxBot/commit/89ac26fee977536e3bf1acf0fb6ff26b179e2361))
* **bot:** log handler and middleware failures instead of printing them ([#40](https://github.com/k0te1ch/PodBoxBot/issues/40)) ([b5ca5ed](https://github.com/k0te1ch/PodBoxBot/commit/b5ca5ed30c7f6c4b1b1bc9ff86054eb3476a0586))
* **bot:** make the admin panel open and navigate again ([#62](https://github.com/k0te1ch/PodBoxBot/issues/62)) ([0557e15](https://github.com/k0te1ch/PodBoxBot/commit/0557e156d0044268eb579358085f2de311d975ce))
* **bot:** repair the mp3 upload path found by a live e2e run ([#45](https://github.com/k0te1ch/PodBoxBot/issues/45)) ([ca6ffa1](https://github.com/k0te1ch/PodBoxBot/commit/ca6ffa1b7a0551801f41d854206d57a780a468c4))
* **ftp:** upload postshow episodes into FTP_POSTSHOW_DIR ([#32](https://github.com/k0te1ch/PodBoxBot/issues/32)) ([af7754d](https://github.com/k0te1ch/PodBoxBot/commit/af7754d395c0fc467ca5f33ce3fc3be64401a69f))
* **logging:** cap docker and file logs and warn admins about a full disk ([#63](https://github.com/k0te1ch/PodBoxBot/issues/63)) ([d4a372c](https://github.com/k0te1ch/PodBoxBot/commit/d4a372cd90a9e8b7e3d53b7b30eac8a636280c0f))
* **logging:** switch loki retention from table_manager to compactor ([#43](https://github.com/k0te1ch/PodBoxBot/issues/43)) ([a0cd433](https://github.com/k0te1ch/PodBoxBot/commit/a0cd4335a52388c0d30335130a8d3e2d3f56e472))

## [0.5.1](https://github.com/k0te1ch/PodBoxBot/compare/v0.5.0...v0.5.1) (2026-06-04)


### Bug Fixes

* **compose:** add restart policy to schema-registry so it recovers after reboot ([#27](https://github.com/k0te1ch/PodBoxBot/issues/27)) ([71d2b69](https://github.com/k0te1ch/PodBoxBot/commit/71d2b6936e83a8bb7c362689464eefbb24187b29))

## [0.5.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.4.1...v0.5.0) (2026-06-04)


### Features

* **reboot:** make stack resilient to host reboots ([#25](https://github.com/k0te1ch/PodBoxBot/issues/25)) ([c9adcd1](https://github.com/k0te1ch/PodBoxBot/commit/c9adcd156a02d5e3ef5149f008fa7eba74f44249))

## [0.4.1](https://github.com/k0te1ch/PodBoxBot/compare/v0.4.0...v0.4.1) (2026-06-02)


### Bug Fixes

* **release-note:** repair changelog broadcast and log bot version ([241f697](https://github.com/k0te1ch/PodBoxBot/commit/241f697d9caf762c3fe9dc34bffff40cdaa59312))

## [0.4.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.3...v0.4.0) (2026-06-01)


### Features

* **boosty:** publish aftershow episodes to Boosty (mp3 + cover, paid level) ([#19](https://github.com/k0te1ch/PodBoxBot/issues/19)) ([e771c6f](https://github.com/k0te1ch/PodBoxBot/commit/e771c6f91dc360d4eb7462e8940496232c428d4f))

## [0.3.3](https://github.com/k0te1ch/PodBoxBot/compare/v0.3.2...v0.3.3) (2026-05-31)


### Features

* **boosty:** add Boosty publisher with tier-based paywall ([#14](https://github.com/k0te1ch/PodBoxBot/issues/14)) ([ff345d1](https://github.com/k0te1ch/PodBoxBot/commit/ff345d1c054fab31a691c0d8a8f037496a677b4f))


### Bug Fixes

* **compose:** default to direct connection over tun2socks ([#16](https://github.com/k0te1ch/PodBoxBot/issues/16)) ([6bee90c](https://github.com/k0te1ch/PodBoxBot/commit/6bee90cac2751c0dcc1d2f16ca9fc04a0ed31448))


### Reverts

* drop Boosty publisher merged in [#14](https://github.com/k0te1ch/PodBoxBot/issues/14) ([8f0b5de](https://github.com/k0te1ch/PodBoxBot/commit/8f0b5decc657b284e7b6e8564501ec0344011181))


### Miscellaneous Chores

* release as 0.3.3 ([#18](https://github.com/k0te1ch/PodBoxBot/issues/18)) ([05e5e21](https://github.com/k0te1ch/PodBoxBot/commit/05e5e21867e58c83e170d278ec001129fd7a49ac))

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
