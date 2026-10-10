# Changelog

## [0.10.0](https://github.com/k0te1ch/PodBoxBot/compare/v0.9.0...v0.10.0) (2026-10-10)


### Features

* **bot:** accept a numeric chat id as the forward chat ([#124](https://github.com/k0te1ch/PodBoxBot/issues/124)) ([518fad7](https://github.com/k0te1ch/PodBoxBot/commit/518fad75a9633a7a5fff1c5f0b1b453f2eb13ac1))
* **bot:** accept a typed publication time next to the time slots ([#143](https://github.com/k0te1ch/PodBoxBot/issues/143)) ([2b023b7](https://github.com/k0te1ch/PodBoxBot/commit/2b023b7e137027def46ea687b63300e475cfb905))
* **bot:** answer a topic removal with one message and undo under the list ([#142](https://github.com/k0te1ch/PodBoxBot/issues/142)) ([9e6fa47](https://github.com/k0te1ch/PodBoxBot/commit/9e6fa47e1e63eb03910baa4c8191708b9e6387ef))
* **bot:** collect listener topics by hashtag into a queue for hosts ([#109](https://github.com/k0te1ch/PodBoxBot/issues/109)) ([4938ceb](https://github.com/k0te1ch/PodBoxBot/commit/4938ceb3cdba289f578665243a0f441fb6083c46))
* **bot:** keep listener topics and questions in one list for hosts ([#122](https://github.com/k0te1ch/PodBoxBot/issues/122)) ([608533e](https://github.com/k0te1ch/PodBoxBot/commit/608533e2a036a87871801bf33f423530364c6704))
* **bot:** keep the publish board in redis across restarts ([#141](https://github.com/k0te1ch/PodBoxBot/issues/141)) ([8426f05](https://github.com/k0te1ch/PodBoxBot/commit/8426f0505fe62ec31ece3ad48d33ba381fafba3f))
* **bot:** let hosts put queued topics to a listener poll ([#112](https://github.com/k0te1ch/PodBoxBot/issues/112)) ([dcdd109](https://github.com/k0te1ch/PodBoxBot/commit/dcdd109b147dd3662f4d3755175848ec2d3e2178))
* **bot:** let listeners suggest a topic through an ephemeral form ([#111](https://github.com/k0te1ch/PodBoxBot/issues/111)) ([e6ecf4a](https://github.com/k0te1ch/PodBoxBot/commit/e6ecf4a59dc81c0414a4ed40b242b215b25bb983))
* **bot:** make the reaction on an accepted topic configurable ([#130](https://github.com/k0te1ch/PodBoxBot/issues/130)) ([3df232a](https://github.com/k0te1ch/PodBoxBot/commit/3df232a5391ecbb19342bfd341b255df40d7b9d8))
* **bot:** open a menu on /start instead of starting an episode ([#133](https://github.com/k0te1ch/PodBoxBot/issues/133)) ([c3e54ff](https://github.com/k0te1ch/PodBoxBot/commit/c3e54ffe2a92e275124fdf1569335c3680a2a200))
* **bot:** pick the recording and publication dates with buttons ([#135](https://github.com/k0te1ch/PodBoxBot/issues/135)) ([fce7d2b](https://github.com/k0te1ch/PodBoxBot/commit/fce7d2b4783e25fe99dd320b52f60fa8c8eac092))
* **bot:** pick the topic reaction at random from a set ([#132](https://github.com/k0te1ch/PodBoxBot/issues/132)) ([e3698f8](https://github.com/k0te1ch/PodBoxBot/commit/e3698f8d6f3c9d9eb972409e6b3681a5aec787fa))
* **bot:** run listener topics on the sdk suggest queue ([#117](https://github.com/k0te1ch/PodBoxBot/issues/117)) ([dd5778a](https://github.com/k0te1ch/PodBoxBot/commit/dd5778a5374449300394065ad9dff565d96a9d5f))
* **bot:** show admins chats by name with a chat card instead of an id ([#127](https://github.com/k0te1ch/PodBoxBot/issues/127)) ([6c3fedc](https://github.com/k0te1ch/PodBoxBot/commit/6c3fedcae1225dc1f50654a99ba175f8db63b355))
* **bot:** show lists and the publication status as tables ([#136](https://github.com/k0te1ch/PodBoxBot/issues/136)) ([a622727](https://github.com/k0te1ch/PodBoxBot/commit/a6227276d724cfee8f4329ba79f72f15f78e365a))
* **bot:** show the episode upload as one status message ([#134](https://github.com/k0te1ch/PodBoxBot/issues/134)) ([33dcc4a](https://github.com/k0te1ch/PodBoxBot/commit/33dcc4aa7bd8855b0b45a9a768b14a08b841664a))


### Bug Fixes

* **bot:** answer a topic command whose message is already gone ([#129](https://github.com/k0te1ch/PodBoxBot/issues/129)) ([d49aff5](https://github.com/k0te1ch/PodBoxBot/commit/d49aff53b0fb2e12330c83c02f183e634938d54c))
* **bot:** answer the ftp button under a replaced file like the other buttons ([#162](https://github.com/k0te1ch/PodBoxBot/issues/162)) ([ef96a1e](https://github.com/k0te1ch/PodBoxBot/commit/ef96a1e9ccd754179ba34e4e0fba0697e230b9c6))
* **bot:** bound the shutdown and stop background work explicitly ([#165](https://github.com/k0te1ch/PodBoxBot/issues/165)) ([000d74b](https://github.com/k0te1ch/PodBoxBot/commit/000d74bd323d051c9304abfee446a4a22e607211))
* **bot:** escape the episode text in the post forwarded to the chat ([#148](https://github.com/k0te1ch/PodBoxBot/issues/148)) ([eeff2bc](https://github.com/k0te1ch/PodBoxBot/commit/eeff2bc70eff66c20e41444dcb7125e44eb45d76))
* **bot:** forward episodes without chapters to the chat ([#126](https://github.com/k0te1ch/PodBoxBot/issues/126)) ([0819d60](https://github.com/k0te1ch/PodBoxBot/commit/0819d60e8dd1177468fa2d7d9e9353c04edaae6f))
* **bot:** keep the latest state when status edits overlap ([#139](https://github.com/k0te1ch/PodBoxBot/issues/139)) ([8329e0f](https://github.com/k0te1ch/PodBoxBot/commit/8329e0fbdd52c6390452df3a1e0a4a644656cdfc))
* **bot:** let admins use the group topic form past the limit and the ban ([#125](https://github.com/k0te1ch/PodBoxBot/issues/125)) ([4f5e5bc](https://github.com/k0te1ch/PodBoxBot/commit/4f5e5bc0ecc359ee6f641a4b8339fe8209170517))
* **bot:** mask secrets in the bot's own messages to admins ([#164](https://github.com/k0te1ch/PodBoxBot/issues/164)) ([a142571](https://github.com/k0te1ch/PodBoxBot/commit/a1425713b0170dc703586901d3535aba1b8892a8))
* **bot:** open host notes from their list ([#121](https://github.com/k0te1ch/PodBoxBot/issues/121)) ([cdf1bf3](https://github.com/k0te1ch/PodBoxBot/commit/cdf1bf3157e3221daae445e0b3b3a58f3f08ab1f))
* **bot:** report errors through the sdk and keep secrets out of logs ([#152](https://github.com/k0te1ch/PodBoxBot/issues/152)) ([ae87477](https://github.com/k0te1ch/PodBoxBot/commit/ae87477665e3982c8dc34a98779fd6a14e0ce466))
* **bot:** return to the menu after a confirmed admin action ([#128](https://github.com/k0te1ch/PodBoxBot/issues/128)) ([976c811](https://github.com/k0te1ch/PodBoxBot/commit/976c811c83bdfd770abe81d61fa0315f3f4ed8c7))
* **bot:** say why the episode number could not be read from ftp ([#146](https://github.com/k0te1ch/PodBoxBot/issues/146)) ([b8c3e5f](https://github.com/k0te1ch/PodBoxBot/commit/b8c3e5f8a912c1befa2ec3c3d1e5841e326b8b00))
* **bot:** start over when a new MP3 arrives mid-episode ([#140](https://github.com/k0te1ch/PodBoxBot/issues/140)) ([4b1856e](https://github.com/k0te1ch/PodBoxBot/commit/4b1856e14e691a8d1463f8176d2bd212158aa57a))
* **bot:** write the bot texts the way a person would ([#137](https://github.com/k0te1ch/PodBoxBot/issues/137)) ([3b0ac4f](https://github.com/k0te1ch/PodBoxBot/commit/3b0ac4f7997917d7c931fa0907a947ea9c267962))
* **publishers:** mask secrets in logs and in errors sent to the bot ([#159](https://github.com/k0te1ch/PodBoxBot/issues/159)) ([7c8d849](https://github.com/k0te1ch/PodBoxBot/commit/7c8d849d2a493df767dd59599c6c582976630cbf))
* **wordpress:** link the saved draft to its editor page ([#131](https://github.com/k0te1ch/PodBoxBot/issues/131)) ([e0534d4](https://github.com/k0te1ch/PodBoxBot/commit/e0534d48a2356b6efbc84481b4de44a5e5cc94df))
* **wordpress:** restore the post title after the podlove episode update ([#169](https://github.com/k0te1ch/PodBoxBot/issues/169)) ([4ab4a50](https://github.com/k0te1ch/PodBoxBot/commit/4ab4a50b4c847715db42f5bca07de12749efb898))

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
