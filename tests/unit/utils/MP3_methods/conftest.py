import pytest
from unittest import mock
import eyed3

@pytest.fixture
def mock_audio_file():
    """Мокаем объект MP3-файла и его теги"""
    mock_file = mock.Mock(spec=eyed3.core.AudioFile)

    # Инициализация мок для тега
    mock_file.tag = None  # Начальное состояние тега — None

    # Мокаем метод initTag, который должен создать новый тег
    def init_tag_mock(version):
        # Создаем мок для тега, который поддерживает eyed3.id3.Tag
        mock_tag = mock.Mock(spec=eyed3.id3.Tag)

        # Добавляем мок для chapters.set
        mock_tag.chapters = mock.Mock()
        mock_tag.chapters.set = mock.Mock()

        # После инициализации тег не должен быть None
        mock_file.tag = mock_tag

    mock_file.initTag.side_effect = init_tag_mock  # Добавляем мок для initTag


    # Мокаем информацию о файле (например, продолжительность)
    mock_file.info.time_secs = 3600000  # 1 час в миллисекундах

    return mock_file
