"""Upload-episode dialog schema, driven by :mod:`dialog_engine`.

This replaces the former aiogram ``UploadFile`` ``StatesGroup``. The flow has
three steps — pick the episode type, send the MP3, send the metadata template —
and the engine owns step order, validation and answer storage.

The aiogram handlers in :mod:`handlers.podcast_handler` still render the
per-language prompts and perform the Telegram-side side effects (download,
tagging, upload); they consult this engine only for navigation and to read the
collected answers.
"""

from dialog_engine import DialogEngine

# Step IDs are referenced by the handlers and the ``OnStep`` filter, so keep
# them as named constants to avoid stringly-typed drift.
TYPE_EPISODE = "type_episode"
MP3 = "mp3"
TEMPLATE = "template"

DIALOG_ID = "upload_file"

# Canonical episode kinds stored in ``session.answers[TYPE_EPISODE]``. The
# display text is rendered per-language by the handlers/keyboards, so the
# ``choices`` values here are just i18n attribute names for reference.
upload_file_engine = DialogEngine.from_list(
    [
        {
            "id": TYPE_EPISODE,
            "type": "choice",
            "text": "ask_typeEpisode",
            "choices": {"main": "main_episode", "aftershow": "episode_aftershow"},
        },
        {
            "id": MP3,
            "type": "file",
            "text": "ask_mp3",
        },
        {
            "id": TEMPLATE,
            "type": "text",
            "text": "ask_template",
        },
    ],
    dialog_id=DIALOG_ID,
)
