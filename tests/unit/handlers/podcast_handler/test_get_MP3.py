from pathlib import Path
import shutil
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message
from app.handlers.podcast_handler import get_MP3
from app.services.context import context
from app.forms.upload_file import UploadFile
from app.services.keyboards import keyboards
from app.config import LANGUAGES
from aiogram_tests.types.dataset import AUDIO, USER, MESSAGE



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
        patch("app.handlers.podcast_handler.FILES_PATH", files_path),
        patch("app.handlers.podcast_handler.PODCAST_PATH", podcast_path),
    ):
        yield files_path, podcast_path


@pytest.fixture
def mock_get_last_post_id():
    with patch("app.handlers.podcast_handler.get_last_post_ID", return_value=42) as mock:
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
):
    files_path, podcast_path = configure_paths
    handler_func = get_MP3
    state = UploadFile.mp3
    mock_file_id = "test_file_id"
    state_data = {"typeEpisode": "main"}

    test_mp3_file = files_path / "test_delete.mp3"
    test_mp3_file.touch()

    # Общие настройки для бота, пользователя, сообщения и состояния
    handler = handler_factory(handler_func, state=state, state_data=state_data)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    audio = AUDIO.as_object(file_id=mock_file_id)
    msg = MESSAGE.as_object(audio=audio, from_user=user)

    # Create a mock for the reply message with `edit_text` mocked
    download_msg_mock = MagicMock(spec=Message)
    download_msg_mock.edit_text = AsyncMock()

    # Patch `Message.reply` to return `download_msg_mock`
    with (
        patch(
            "app.handlers.podcast_handler.Message.reply",
            new=AsyncMock(side_effect=lambda *args, **kwargs: download_msg_mock),
        ) as mock_reply,
        patch("app.handlers.podcast_handler.LOCAL", new=LOCAL)
    ):

        with patch("shutil.move") as mock_move, patch("app.handlers.podcast_handler.Bot.download") as mock_download:
            if LOCAL:
                with patch(
                    "app.handlers.podcast_handler.Bot.get_file",
                    return_value=MagicMock(file_path="/music/test_file.mp3"),
                ):
                    calls = await bot.query(message=msg)
                    mock_move.assert_called_once()
            else:
                calls = await bot.query(message=msg)
                mock_download.assert_called_once_with(mock_file_id, podcast_path, timeout=60)

            state_context = await state_context_factory(handler, message=msg)

            # Проверка удаления файлов MP3 в директории files_path
            assert not test_mp3_file.exists(), "Temporary MP3 file was not deleted"

            # Проверка удаления файлов MP3 в директории files_path
            assert all(
                not item.suffix == ".mp3" for item in files_path.iterdir()
            ), "Previous MP3 files were not deleted"

            # Проверка изменения состояния FSM
            assert (
                await state_context.get_state() == UploadFile.template
            ), "FSM state did not update to UploadFile.template as expected"

            # Проверка текста сообщения и клавиатуры
            number_last_episode = "43"  # так как `get_last_post_ID` вернул 42
            expected_text = context.ask_template["main"].replace("600", number_last_episode)

            sent_message = calls.send_message.fetchone()
            assert sent_message.text == expected_text, "Sent message text does not match expected ask_template"
            assert (
                sent_message.reply_markup == keyboards["podcast_handler"][language].cancel
            ), "Keyboard does not match expected 'cancel' keyboard"

            mock_reply.assert_called_once_with(context[language].got_mp3)

            # Verify `edit_text` was called on the reply message
            download_msg_mock.edit_text.assert_called_once_with(context[language].downloaded)
