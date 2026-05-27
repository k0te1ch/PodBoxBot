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

The MP3 upload step uses Telethon directly because tgtest's YAML step
actions don't include file upload as of this writing.

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

## Notes

- **No CI wiring** — these are local-only on purpose (real creds, real
  Telegram rate limits, real FTP/WP side effects).
- The test user account must be in the bot's `IsAdmin` whitelist —
  `podcast_handler` is admin-gated.
- Each pipeline test publishes for real. Use a throwaway WP/FTP target.
- If tgtest's helper API (e.g. `chat.click(data=...)`, `expect(buttons=...)`)
  diverges from what's used here, adjust — README in upstream tgtest is the
  source of truth.
