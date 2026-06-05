import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from aiogram_tests.types.dataset import AUDIO, MESSAGE, USER

from config import LANGUAGES
from forms.upload_file import MP3, TEMPLATE, upload_file_engine
from handlers.podcast_handler import get_MP3
from services import context, keyboards
from utils.dialog import SESSION_KEY


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as temp:
        yield temp


@pytest.fixture
def configure_paths(temp_dir):
    temp_path = Path(temp_dir)
    files_path = temp_path / "files"
    podcast_path = temp_path / "podcast" / "podcast.mp3"
    files_path.mkdir(parents=True, exist_ok=True)
    podcast_path.mkdir(parents=True, exist_ok=True)

    with (
        patch("handlers.podcast_handler.FILES_PATH", files_path),
        patch("handlers.podcast_handler.PODCAST_PATH", podcast_path),
    ):
        yield files_path, podcast_path


@pytest.fixture
def mock_get_last_post_id():
    with patch("handlers.podcast_handler.get_last_post_ID", new_callable=AsyncMock, return_value=42) as mock:
        yield mock


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("LOCAL", [True, False])
async def test_get_MP3_handler(
    username,
    language,
    LOCAL,
    handler_factory,
    bot_factory,
    state_context_factory,
    configure_paths,
    mock_get_last_post_id,
    dialog_state,
    session_state_data,
):
    files_path, podcast_path = configure_paths
    mock_file_id = "test_file_id"
    # Session sits on the mp3 step with the episode type already chosen.
    state_data = session_state_data(step=MP3, type_episode="main")

    test_mp3_file = files_path / "test_delete.mp3"
    test_mp3_file.touch()

    handler = handler_factory(get_MP3, state=dialog_state, state_data=state_data)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    audio = AUDIO.as_object(file_id=mock_file_id)
    msg = MESSAGE.as_object(audio=audio, from_user=user)

    # Create a mock for the reply message with `edit_text` mocked
    download_msg_mock = MagicMock(spec=Message)
    download_msg_mock.edit_text = AsyncMock()

    # Patch the download pipeline. ``get_file`` is awaited unconditionally and
    # ``monitor_file_progress`` decides whether the upload succeeded, so both
    # must be mocked regardless of the LOCAL branch.
    with (
        patch(
            "handlers.podcast_handler.Message.reply",
            new=AsyncMock(side_effect=lambda *args, **kwargs: download_msg_mock),
        ) as mock_reply,
        patch("handlers.podcast_handler.LOCAL", new=LOCAL),
        patch("handlers.podcast_handler.monitor_file_progress", new=AsyncMock(return_value=True)),
        patch(
            "handlers.podcast_handler.Bot.get_file",
            new=AsyncMock(return_value=MagicMock(file_path="/music/test_file.mp3")),
        ),
        patch("handlers.podcast_handler.Bot.download", new=AsyncMock()) as mock_download,
        patch("shutil.move") as mock_move,
    ):
        calls = await bot.query(message=msg)
        if LOCAL:
            mock_move.assert_called_once()
        else:
            mock_download.assert_called_once_with(mock_file_id, podcast_path, timeout=60)

        state_context = await state_context_factory(handler, message=msg)

        # Проверка удаления файлов MP3 в директории files_path
        assert not test_mp3_file.exists(), "Temporary MP3 file was not deleted"
        assert all(item.suffix != ".mp3" for item in files_path.iterdir()), "Previous MP3 files were not deleted"

        # The engine recorded the uploaded file and advanced to the template step.
        session = upload_file_engine.restore_session((await state_context.get_data())[SESSION_KEY])
        assert session.answers[MP3] == [mock_file_id]
        assert upload_file_engine.current_step(session).id == TEMPLATE

        # Проверка текста сообщения и клавиатуры
        number_last_episode = "43"  # так как `get_last_post_ID` вернул 42
        expected_text = context[language].ask_template["main"].replace("600", number_last_episode)

        sent_message = calls.send_message.fetchone()
        assert sent_message.text == expected_text, "Sent message text does not match expected ask_template"
        assert sent_message.reply_markup == keyboards["podcast_handler"][language].cancel, (
            "Keyboard does not match expected 'cancel' keyboard"
        )

        mock_reply.assert_called_once_with(context[language].got_mp3)

        # Verify `edit_text` was called on the reply message
        download_msg_mock.edit_text.assert_called_once_with(context[language].downloaded)
