# PodBoxBot

Telegram-бот для подкаст-команды [«Разговорный жанр»](https://podbox.ru/) —
автоматизирует рутину публикации эпизода: тегирование mp3, заливка на FTP
хостинга, создание поста-черновика в WordPress с Podlove-метаданными
и chapters, пересылка анонса в чат.

Стек микросервисный: бот собирает запрос → шлёт в Kafka → отдельные
publisher-сервисы (FTP, WordPress) забирают и выполняют → возвращают
результат через Kafka → бот апдейтит сообщение в Telegram. Полное
наблюдение через Prometheus + Loki + Grafana.

## Что внутри

```
app/
├── bot/                  # aiogram 3 бот: хендлеры, FSM, клавиатуры, i18n (FTL)
├── publishers/
│   ├── FTP/              # консьюмер publisher.ftp.upload → ftp upload → publisher.ftp.result
│   └── WordPress/        # консьюмер publisher.wordpress.upload → WP post-new form
│                         #   + Podlove REST API (Application Password) для метаданных
│                         #   и chapters → publisher.wordpress.result
├── kafka/                # kafka-init: создаёт топики из topics.yaml при старте кластера
├── schema-watcher/       # регистрирует Avro-схемы в Schema Registry
└── shared/
    ├── config/           # pydantic-settings, один источник правды для микросервисов
    └── kafka/            # общий KafkaProducer/Consumer + Avro-схемы
configs/                  # prometheus.yml, loki, grafana datasources, alloy
docker-compose.yml        # стек С tun2socks (для хостов за блокировкой)
docker-compose.direct.yml # стек БЕЗ tun2socks (для хостов с прямым доступом)
utils/bootstrap.sh        # первичный деплой на чистый prod
.env.example              # шаблон переменных окружения
```

## Поток данных

```
Telegram user
    │
    ▼
podboxbot_bot ──► Kafka topic publisher.{ftp,wordpress}.upload
                                                     │
                                                     ▼
                                       podboxbot_publisher_{ftp,wordpress}
                                                     │
                                                     ▼
                            Kafka topic publisher.{ftp,wordpress}.result
                                                     │
                                                     ▼
                                       podboxbot_bot (Telegram edit_message)
```

Схемы сообщений (`app/shared/kafka/schemas/*.avsc`) регистрируются
`schema-watcher`'ом автоматически при старте.

## Развёртывание на чистом prod-сервере

### Минимальные требования

- Linux (Debian/Ubuntu проверены).
- `docker` ≥ 23, `docker compose` v2, `curl`, `jq`, `bash` ≥ 4.
- ~4 ГБ RAM свободно для всего стека (Kafka, Grafana, Loki — основные едоки).

Если у тебя только `docker-compose` v1 — поставь плагин v2:

```bash
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version   # должно показать v2.x
```

### Шаги

1. **Клонировать репо и перейти на `dev`:**

   ```bash
   git clone https://github.com/k0te1ch/PodBoxBot.git
   cd PodBoxBot
   git checkout dev
   ```

2. **Подготовить `.env`:**

   ```bash
   cp .env.example .env
   nano .env
   ```

   Минимум, что надо заполнить (остальное — опционально или со значениями
   по умолчанию):

   | Переменная | Что это |
   |---|---|
   | `TELEGRAM_API_TOKEN` | токен бота от @BotFather |
   | `TELEGRAM_SERVER_API_ID` / `_HASH` | для self-hosted telegram-bot-api ([my.telegram.org](https://my.telegram.org)) |
   | `FORWARD_CHAT_USERNAME` | username публичной группы/канала (формат `@group`), куда бот будет форвардить анонсы |
   | `ADMINS_ID` | список ID Telegram-юзеров, которым разрешено пользоваться |
   | `FTP_SERVER` / `FTP_LOGIN` / `FTP_PASSWORD` | креды FTP-хостинга |
   | `WP_URL` / `WP_LOGIN` / `WP_PASSWORD` | креды WordPress-юзера для form-логина |
   | `WP_APP_PASSWORD` | **Application Password** для REST API (WP Admin → Users → Profile → Application Passwords) |
   | `REDIS_PASSWORD` | произвольный, для встроенного redis |
   | `LOCAL` | `True` если телеграм-API локальный |

3. **Выбрать compose-файл:**

   - Хост в РФ / за блокировкой и есть SOCKS-прокси (например xray на
     `localhost:10808`) → используй дефолтный `docker-compose.yml`
     (заворачивает трафик telegram-bot-api через `tun2socks`).
   - Хост за рубежом / есть прямой доступ к Telegram DC →
     `docker-compose.direct.yml` (без прокси-слоя).

4. **Запустить bootstrap:**

   ```bash
   chmod +x utils/bootstrap.sh

   # С tun2socks (дефолт)
   ./utils/bootstrap.sh

   # Без tun2socks
   ./utils/bootstrap.sh -f docker-compose.direct.yml
   ```

   Скрипт проходит 7 фаз:
   1. Preflight: проверка docker/compose/curl/jq, `.env`, ключей по `.env.example`.
   2. Backup существующих volumes в `./backups/<utc-ts>/` (на первом запуске пропускается).
   3. `docker compose pull + build`.
   4. Поэтапный `up`: kafka → wait healthy → schema-registry → wait healthy
      → kafka-init → wait exit 0 → schema-watcher → sleep 60s → остальное.
   5. Verify topics: сверка с `app/kafka/topics.yaml`.
   6. Verify schemas: сверка с `app/shared/kafka/schemas/*.avsc`.
   7. Smoke pub/sub через временный топик `bootstrap.smoke.<ts>`.

   Скрипт идемпотентен — повторный запуск ничего не ломает.

### Что доступно после успешного запуска

| Сервис | URL | Зачем |
|---|---|---|
| Grafana | `http://<host>:3000` (admin/admin) | Дашборды по бот/publisher метрикам, логи из Loki |
| Kafdrop | `http://<host>:9000` | UI для Kafka — посмотреть топики, оффсеты, сообщения |
| Telegram бот | в Telegram | пишешь боту, проверяешь сценарии |

### Апгрейд

`bootstrap.sh` рассчитан на **первый** деплой. На горячий апгрейд:

```bash
git pull
docker compose build --no-cache bot publisher_ftp publisher_wordpress
docker compose up -d
```

## Разработка

- Локальные venv'ы по сервисам:
  - `cd app/bot && poetry install --with testing,dev`
  - `cd app/publishers/FTP && poetry install`
  - `cd app/publishers/WordPress && poetry install`
- Lint: `poetry -C app/bot run ruff check app`
- Unit-тесты: `poetry -C app/bot run pytest tests/unit -q`
- Ветки: `WIP` (активная работа) → `dev` (тестируется на проде) → `main`
  (стабильная). Никогда не пушим напрямую в `main`.
- Коммиты: [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat(...)`, `fix(...)`, `refactor(...)`, `chore(...)`).

## Лицензия

См. `LICENSE`.
