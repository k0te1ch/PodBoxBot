from datetime import datetime
from pathlib import Path
from unittest import mock

import eyed3
import pytest
import pytz

from config import (
    PODCAST_CITY,
    PODCAST_COUNTRY,
    PODCAST_DISTRICT,
    PODCAST_GENRE,
    PODCAST_LINK,
    PODCAST_NAME,
    SUPPORT_LINK,
    TIMEZONE,
)
from utils.MP3_methods import audio_tag


@pytest.fixture
def mock_paths():
    """Мокаем только те объекты, которые реально используются"""
    with (
        mock.patch("utils.MP3_methods.PODCAST_PATH", Path("/mocked/podcast.mp3")),
        mock.patch("utils.MP3_methods.COVER_RZ_PATH", Path("/mocked/cover_rz.jpg")),
        mock.patch("utils.MP3_methods.COVER_PS_PATH", Path("/mocked/cover_ps.jpg")),
        mock.patch("utils.MP3_methods.PODCAST_GENRE", 186),
        mock.patch("utils.MP3_methods.TIMEZONE", pytz.timezone("Europe/Moscow")),
    ):
        yield


def check_common_tag_settings(mock_audio_file, expected_title, expected_comment, year):
    """Проверка общих настроек тегов"""
    # Проверка основных тегов
    assert mock_audio_file.tag.artist == PODCAST_NAME, "Artist tag was not set correctly"
    assert mock_audio_file.tag.album == PODCAST_NAME, "Album tag was not set correctly"
    assert mock_audio_file.tag.title == expected_title, f"Title tag was not set correctly: {expected_title}"
    assert mock_audio_file.tag.genre == PODCAST_GENRE, "Genre tag was not set correctly"

    # Проверка комментариев
    mock_audio_file.tag.comments.set.assert_called_with(expected_comment)
    mock_audio_file.tag.lyrics.set.assert_called_with(expected_comment)

    # Проверка вызовов методов для URL и изображений
    mock_audio_file.tag.user_url_frames.set.assert_called_once()
    mock_audio_file.tag.images.set.assert_called_once()

    # Проверка дополнительных полей
    assert mock_audio_file.tag.copyright == PODCAST_NAME, "Copyright tag was not set correctly"
    assert mock_audio_file.tag.publisher == PODCAST_NAME, "Publisher tag was not set correctly"
    assert mock_audio_file.tag.original_release_date == year, "Original release date was not set correctly"
    assert mock_audio_file.tag.release_date == year, "Release date was not set correctly"
    assert mock_audio_file.tag.recording_date == year, "Recording date was not set correctly"
    assert mock_audio_file.tag.album_type == "single", "Album type was not set correctly"

    # Проверка ссылок
    assert mock_audio_file.tag.artist_url == PODCAST_LINK, "Artist URL was not set correctly"
    assert mock_audio_file.tag.commercial_url == SUPPORT_LINK, "Commercial URL was not set correctly"
    assert mock_audio_file.tag.payment_url == SUPPORT_LINK, "Payment URL was not set correctly"

    # Проверка происхождения артиста
    assert mock_audio_file.tag.artist_origin == eyed3.core.ArtistOrigin(
        PODCAST_CITY, PODCAST_DISTRICT, PODCAST_COUNTRY
    ), "Artist origin was not set correctly"


@pytest.mark.parametrize(
    "audio_type, expected_cover_path", [("main", Path("/mocked/cover_rz.jpg")), ("ps", Path("/mocked/cover_ps.jpg"))]
)
@mock.patch("eyed3.load")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"mocked_image_data")
def test_audio_tag(mock_open, mock_eyed3_load, mock_audio_file, mock_paths, audio_type, expected_cover_path):
    """Параметризованное тестирование обработки MP3-файла для различных типов"""
    mock_eyed3_load.return_value = mock_audio_file

    # Мокаем существующий тег
    mock_audio_file.tag = mock.Mock(spec=eyed3.id3.Tag)

    info = {
        "title": "Test Title",
        "comment": "Test Comment",
        "chapters": [{"start_time": 0, "end_time": 60, "title": "Chapter 1"}],
    }

    # Вызов функции
    audio_tag(info, audio_type)

    # Проверка очищения тега
    mock_audio_file.tag.clear.assert_called_once()

    # Проверка установки тегов
    check_common_tag_settings(mock_audio_file, "Test Title", "Test Comment", datetime.now(TIMEZONE).year)

    # Проверка открытия правильного файла обложки в зависимости от типа
    mock_open.assert_called_once_with(expected_cover_path, "rb")

    # Проверка сохранения тегов
    mock_audio_file.tag.save.assert_called_once()


@pytest.mark.parametrize("tag_exists", [True, False])
@pytest.mark.parametrize(
    "audio_type, expected_cover_path", [("main", Path("/mocked/cover_rz.jpg")), ("ps", Path("/mocked/cover_ps.jpg"))]
)
@mock.patch("eyed3.load")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"mocked_image_data")
def test_audio_tag_tag_handling(
    mock_open, mock_eyed3_load, mock_audio_file, mock_paths, tag_exists, audio_type, expected_cover_path
):
    """Тестирование обработки случая, когда тег отсутствует или существует"""
    mock_eyed3_load.return_value = mock_audio_file

    # Мокаем сценарий с отсутствием или наличием тега
    if tag_exists:
        mock_audio_file.tag = mock.Mock(spec=eyed3.id3.Tag)
    else:
        mock_audio_file.tag = None

    info = {
        "title": "Test Title",
        "comment": "Test Comment",
        "chapters": [{"start_time": 0, "end_time": 60, "title": "Chapter 1"}],
    }

    # Вызов функции
    audio_tag(info, audio_type)

    if tag_exists:
        # Проверяем, что при наличии тега, он был очищен
        mock_audio_file.tag.clear.assert_called_once()
    else:
        # Проверка инициализации тега, если его не было
        mock_audio_file.initTag.assert_called_once_with((2, 4, 0))

    # Проверка открытия файла обложки
    mock_open.assert_called_once_with(expected_cover_path, "rb")

    # Проверка сохранения тегов
    mock_audio_file.tag.save.assert_called_once()


@pytest.mark.parametrize(
    "info, expected_title, expected_comment",
    [
        ({"title": "Test Title", "comment": "Test Comment", "chapters": []}, "Test Title", "Test Comment"),
        ({"title": "Title Only", "comment": "", "chapters": []}, "Title Only", ""),
        ({"title": "", "comment": "No Title", "chapters": []}, "", "No Title"),
    ],
)
@pytest.mark.parametrize(
    "audio_type, expected_cover_path", [("main", Path("/mocked/cover_rz.jpg")), ("ps", Path("/mocked/cover_ps.jpg"))]
)
@mock.patch("eyed3.load")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"mocked_image_data")
def test_audio_tag_variable_info(
    mock_open,
    mock_eyed3_load,
    mock_audio_file,
    mock_paths,
    info,
    expected_title,
    expected_comment,
    audio_type,
    expected_cover_path,
):
    """Тестирование различных вариантов данных в info"""
    mock_eyed3_load.return_value = mock_audio_file
    mock_audio_file.tag = mock.Mock(spec=eyed3.id3.Tag)

    # Вызов функции
    audio_tag(info, audio_type)

    # Проверка установки тегов
    check_common_tag_settings(mock_audio_file, expected_title, expected_comment, datetime.now(TIMEZONE).year)

    # Проверка открытия файла обложки
    mock_open.assert_called_once_with(expected_cover_path, "rb")

    # Проверка сохранения тегов
    mock_audio_file.tag.save.assert_called_once()


# Тестирование логирования ошибок при проблемах с загрузкой файла
@mock.patch("eyed3.load", side_effect=Exception("Error loading file"))
def test_audio_tag_load_error(mock_eyed3_load, caplog):
    """Тестирование логирования ошибок при загрузке MP3-файла"""
    info = {"title": "Test Title", "comment": "Test Comment", "chapters": []}

    # Вызов функции с ошибкой загрузки
    with caplog.at_level("ERROR"):
        audio_tag(info, "main")

    # Проверка логирования ошибки
    assert any("Error loading file" in message for message in caplog.messages), (
        "Expected error message not found in logs"
    )


@mock.patch("eyed3.load")
@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_audio_tag_cover_error(mock_open, mock_eyed3_load, mock_audio_file, caplog, mock_paths):
    """Тестирование ошибки при открытии файла обложки"""
    mock_eyed3_load.return_value = mock_audio_file

    # Симуляция ошибки при открытии файла обложки
    mock_open.side_effect = OSError("Error opening cover file")

    info = {
        "title": "Test Title",
        "comment": "Test Comment",
        "chapters": [{"start_time": 0, "end_time": 60, "title": "Chapter 1"}],
    }

    with caplog.at_level("ERROR"):
        audio_tag(info, "main")

    # Проверка, что ошибка была залогирована
    assert "Error opening cover file" in caplog.text


@mock.patch("eyed3.load", return_value=None)
def test_audio_tag_file_not_found(mock_eyed3_load, caplog, mock_paths):
    """Тестирование обработки случая, когда файл не загружается (audio_file = None)"""
    info = {"title": "Test Title", "comment": "Test Comment", "chapters": []}

    with caplog.at_level("ERROR"):
        audio_tag(info, "main")

    # Проверка, что ошибка была залогирована
    assert "Audio file not found or could not be loaded" in caplog.text
