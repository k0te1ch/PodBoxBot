# E2E tests

Driven by [tgtest](https://github.com/k0te1ch/tgtest) — a Telethon-based
"real user talks to your bot" harness. Tests live here and are **excluded
from the default `pytest` run** (`addopts = -m 'not e2e'` in
`app/bot/pyproject.toml`).

## What's covered

- `scenarios/start_menu.yaml` — smoke: `/start` opens the episode-type menu.
- `test_full_pipeline.py` — full pipeline (no chat forwarding):
  - `test_full_pipeline_ftp` — start → choose type → upload MP3 → template → click **FTP menu → FTP upload**.
  - `test_full_pipeline_wordpress` — same flow ending in **WP menu → WP upload**.
- `test_listener_topics.py` — listener topics, only with `E2E_TOPICS=1` and a
  bot started with `TOPICS_ENABLED=true`:
  - the private-chat form (`/start topic`) puts a topic into the queue, the
    admin takes it from `/admin` into episode 999 and the author gets the
    notice with that number;
  - `/topic` and `/тема` in the private chat open the same form;
  - with `E2E_TOPICS_CHAT` (a group with the bot as admin and the test
    account, equal to the bot's `TOPICS_CHAT`, `@username` or numeric id):
    - `#тема` in the group gets a reaction and shows up in the queue;
    - the ephemeral form (`/topic` sent as an ephemeral command, the topic as
      an ephemeral reply, the confirm button) puts a topic into the queue;
    - a poll of three topics is published from `/admin`, gets a vote and is
      closed with the button: the winner is taken and both the author and
      the hosts are told.
  Ephemeral messages go through raw Telethon requests, tgtest has no helper
  for them. What other members of the group see, and how a client without
  ephemeral messages behaves, is still checked by hand. A poll that closes
  on its timer takes at least an hour (`TOPICS_POLL_HOURS=1`) and is not in
  the suite.
  Set `TOPICS_DAILY_LIMIT=0` on the test bot: every run suggests more than
  three topics from the same account.

Everything goes through tgtest (0.2+): the MP3 upload uses `chat.send_file`,
menu edits are checked with `expect_edit` / `wait_until`, and the account
language comes from `E2E_LANG` via `TG_LANG_CODE`.

## One-time setup

1. Install deps (from `app/bot/`): `poetry install --with testing`.
2. Get Telegram API credentials at <https://my.telegram.org> for the
   **test user account** (not the bot — bots cannot read other bots).
3. Copy `.env.example` to `tests/e2e/.env` and fill in.
4. Place a real MP3 file at `tests/e2e/fixtures/sample.mp3`. The handler
   downloads via the bot API, so it must be a valid MP3 the bot can
   process (eyed3-readable).
5. Run interactive login once so Telethon writes a session file:
   ```sh
   poetry run python -c "from telethon import TelegramClient; import os; TelegramClient(os.environ['TG_SESSION'], int(os.environ['TG_API_ID']), os.environ['TG_API_HASH']).start(phone=os.environ['TG_PHONE'])"
   ```
   Or use tgtest's bundled login script if present in your install.

## Running

Bring up the bot locally (`docker compose up -d --build` or your usual
flow) — these tests talk to a **live, running** bot.

```sh
# everything
poetry run pytest tests/e2e -m e2e

# just the YAML smoke
poetry run tgtest run tests/e2e/scenarios/start_menu.yaml

# one pipeline
poetry run pytest tests/e2e/test_full_pipeline.py::test_full_pipeline_ftp -m e2e
```

### Isolated stand

`docker-compose.e2e.yml` swaps the real FTP/WordPress for local stubs, so a
run never publishes anywhere: SFTP on `sftp:2222` for the publisher, FTPS on
`sftp:21` for the bot (same storage), WordPress pointed at a dead address.
Telegram goes through tun2socks, as in production; set its `PROXY` to your
local proxy if DC traffic is blocked.

```sh
docker compose -p podbox-e2e -f docker-compose.tun2socks.yml -f tests/e2e/docker-compose.e2e.yml \
  up -d --build bot publisher_ftp publisher_wordpress sftp ftps
# the bot needs at least one episode on FTP to compute the next number
docker exec podbox-e2e-sftp-1 sh -c 'touch /config/600_rz_seed.mp3 && chown 1000:1000 /config/600_rz_seed.mp3'
```

The test account's messages are matched against the bot's own `.ftl`
strings in `E2E_LANG` (default `ru`); the client connects with that
`lang_code` so the bot answers in the same language.

## Notes

- **No CI wiring** — these are local-only on purpose (real creds, real
  Telegram rate limits, real FTP/WP side effects).
- The test user account must be in the bot's `IsAdmin` whitelist —
  `podcast_handler` is admin-gated.
- Each pipeline test publishes for real. Use a throwaway WP/FTP target.
- If tgtest's helper API (e.g. `chat.click(data=...)`, `expect(buttons=...)`)
  diverges from what's used here, adjust — README in upstream tgtest is the
  source of truth.
