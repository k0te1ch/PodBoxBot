import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from aiogram_tests.requester import Calls
from aiogram_tests.types.dataset import MESSAGE, USER
from app.forms.upload_file import UploadFile
from app.handlers.podcast_handler import set_template
from app.services.context import context
from app.services.keyboards import keyboards


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as temp:
        yield temp


@pytest.fixture
def mock_validate_template():
    with patch("app.handlers.podcast_handler.validate_template") as mock:
        yield mock


@pytest.fixture
def mock_audio_tag():
    with patch("app.handlers.podcast_handler.audio_tag") as mock:
        yield mock


@pytest.fixture
def configure_paths(temp_dir):
    files_path = Path(temp_dir) / "files"
    files_path.mkdir(parents=True, exist_ok=True)

    with patch("app.handlers.podcast_handler.FILES_PATH", files_path):
        yield files_path


@pytest.mark.asyncio
@pytest.mark.parametrize("typeEpisode", ["main", "aftershow"])
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", ["en", "ru"])
async def test_set_template(
    handler_factory,
    bot_factory,
    state_context_factory,
    configure_paths,
    mock_validate_template,
    mock_audio_tag,
    typeEpisode,
    username,
    language,
):
    state_data = {"typeEpisode": typeEpisode}

    # Настроим mock-ответ от validate_template для успешного кейса
    valid_info = {"number": "42", "title": "Podcast Episode Title"}
    mock_validate_template.return_value = valid_info

    # Создаём моки для бота, пользователя, сообщения и состояния
    handler = handler_factory(set_template, state=UploadFile.template, state_data=state_data)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="Some valid template text", from_user=user)

    # Мокируем ответ от msg.answer
    temp_msg_mock = MagicMock(spec=Message)
    temp_msg_mock.delete = AsyncMock()

    with patch(
        "app.handlers.podcast_handler.Message.answer",
        new=AsyncMock(return_value=temp_msg_mock),
    ):
        with patch("pathlib.Path.rename") as mock_rename:
            with patch("pathlib.Path.exists", return_value=True):  # Мокируем существование файла
                with patch("pathlib.Path.stat", return_value=MagicMock(st_size=12345)):
                    with patch("eyed3.load") as mock_eyed3_load:
                        # Мокируем возвращаемый объект от eyed3.load
                        mock_af = MagicMock()
                        mock_af.info.time_secs = 123
                        mock_af.tag.artist = "Test Artist"  # Мокируем корректное значение для исполнителя
                        mock_eyed3_load.return_value = mock_af

                        # Запускаем тестируемый обработчик
                        calls: Calls = await bot.query(message=msg)

                        # Проверяем вызов validate_template
                        mock_validate_template.assert_called_once_with(msg.text)

                        # Проверяем вызов аудиотегирования
                        mock_audio_tag.assert_called_once_with(valid_info, typeEpisode)

                        # Проверяем переименование файла
                        mock_rename.assert_called_once()
                        new_file_name = f"0042_{'rz' if typeEpisode == 'main' else 'postshow'}_{datetime.now().strftime('%d%m%Y')}.mp3"
                        assert mock_rename.call_args.args[0].name == new_file_name

                        # Проверяем удаление временного сообщения
                        temp_msg_mock.delete.assert_called()

                        # Проверяем отправку аудиофайла
                        mp3_reply = calls.send_audio.fetchone()
                        assert mp3_reply.caption == context[language].done_mp3
                        assert mp3_reply.reply_markup == (
                            keyboards["podcast_handler"][language].audio_menu_main
                            if typeEpisode == "main"
                            else keyboards["podcast_handler"][language].audio_menu_post
                        )

                        # Проверяем, что состояние было очищено
                        state_context = await state_context_factory(handler, message=msg)
                        assert await state_context.get_state() is None, "State was not cleared"


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", ["en", "ru"])
async def test_set_template_invalid_input(
    handler_factory,
    bot_factory,
    state_context_factory,
    configure_paths,
    mock_validate_template,
    username,
    language,
):
    state_data = {"typeEpisode": "main"}

    # Устанавливаем mock-ответ validate_template как None для проверки обработки невалидного ввода
    mock_validate_template.return_value = None

    # Создаём моки для бота, пользователя, сообщения и состояния
    handler = handler_factory(set_template, state=UploadFile.template, state_data=state_data)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="Invalid template", from_user=user)

    # Мокаем метод msg.reply
    with patch("app.handlers.podcast_handler.Message.reply", new=AsyncMock()) as mock_reply:
        calls: Calls = await bot.query(message=msg)

        # Проверяем вызов validate_template
        mock_validate_template.assert_called_once_with(msg.text)

        # Проверяем ответ с сообщением об ошибке
        mock_reply.assert_called_once_with(context[language].invalid_input)

        # Проверяем, что никакой файл не был отправлен
        attrs = calls._get_attributes()
        assert "send_audio" not in attrs, "Audio should not be sent on invalid input"
