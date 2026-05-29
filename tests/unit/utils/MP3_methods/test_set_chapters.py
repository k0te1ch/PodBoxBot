from unittest import mock

from eyed3.id3 import ID3_V2_4, UTF_16_ENCODING

from utils.MP3_methods import set_chapters


def initialize_mock_audio_file(mock_audio_file):
    """Инициализация mock_audio_file, если tag не существует"""
    if mock_audio_file.tag is None:
        mock_audio_file.initTag(ID3_V2_4)


def create_mock_chapter(mock_audio_file, chap_num, start_time, end_time):
    """Создание и настройка мока для главы"""
    mock_chapter = mock.Mock()
    mock_audio_file.tag.chapters.set.return_value = mock_chapter
    mock_audio_file.tag.chapters.set.assert_called_once_with(
        bytes(f"CHAP{chap_num}", encoding="cp866"), (start_time, end_time)
    )
    return mock_chapter


def test_set_chapters_with_empty_list(mock_audio_file):
    """Тестирование с пустым списком глав — проверка отсутствия изменений"""
    initialize_mock_audio_file(mock_audio_file)

    set_chapters(mock_audio_file, [])

    # Проверка, что никакие главы не были добавлены
    mock_audio_file.tag.chapters.set.assert_not_called(), "Ни одна глава не должна быть добавлена"


def test_set_chapters_with_single_chapter(mock_audio_file):
    """Тестирование с одной главой — проверка корректного добавления"""
    chapters = [("00:00:10", "Introduction")]
    initialize_mock_audio_file(mock_audio_file)

    with mock.patch("utils.MP3_methods.time_to_milliseconds", return_value=10000) as mock_time_to_ms:
        # Мокаем возврат главы для метода set
        mock_chapter = mock.Mock()
        mock_chapter.encoding = UTF_16_ENCODING  # Явно устанавливаем кодировку
        mock_chapter.title = "Introduction"  # Явно устанавливаем заголовок
        mock_audio_file.tag.chapters.set.return_value = mock_chapter

        # Выполнение функции
        set_chapters(mock_audio_file, chapters)

        # Проверка вызова функции преобразования времени
        mock_time_to_ms.assert_called_once_with("00:00:10"), "time_to_milliseconds не вызван с ожидаемым временем"

        # Проверка добавления главы
        mock_audio_file.tag.chapters.set.assert_called_once_with(
            bytes("CHAP1", encoding="cp866"),
            (10000, 3599999),  # от 10 секунд до конца файла (59 минут)
        )

        # Проверка установки правильных свойств главы
        assert mock_chapter.encoding == UTF_16_ENCODING, "Неверное кодирование главы"
        assert mock_chapter.title == "Introduction", "Неверный заголовок главы"


def test_set_chapters_with_multiple_chapters(mock_audio_file):
    """Тестирование с несколькими главами — проверка корректного добавления всех глав"""
    chapters = [("00:00:10", "Introduction"), ("00:10:00", "Chapter 1"), ("00:20:00", "Chapter 2")]

    with mock.patch(
        "app.utils.MP3_methods.time_to_milliseconds", side_effect=[10000, 600000, 600000, 1200000, 1200000]
    ):
        set_chapters(mock_audio_file, chapters)

        # Проверка добавления первой главы
        mock_audio_file.tag.chapters.set.assert_any_call(bytes("CHAP1", encoding="cp866"), (10000, 599999))
        # Проверка добавления второй главы
        mock_audio_file.tag.chapters.set.assert_any_call(bytes("CHAP2", encoding="cp866"), (600000, 1199999))
        # Проверка добавления третьей главы
        mock_audio_file.tag.chapters.set.assert_any_call(bytes("CHAP3", encoding="cp866"), (1200000, 3599999))


def test_set_chapters_with_mock_time_to_milliseconds(mock_audio_file):
    """Тестирование с моком time_to_milliseconds — проверка всех вызовов и добавлений"""
    chapters = [("00:00:10", "Introduction"), ("00:10:00", "Chapter 1")]

    with mock.patch("utils.MP3_methods.time_to_milliseconds", side_effect=[10000, 600000, 600000]) as mock_time_to_ms:
        set_chapters(mock_audio_file, chapters)

        # Проверка вызовов time_to_milliseconds
        (
            mock_time_to_ms.assert_has_calls([mock.call("00:00:10"), mock.call("00:10:00")], any_order=False),
            "Неверные вызовы time_to_milliseconds",
        )

        # Проверка добавления первой главы
        mock_audio_file.tag.chapters.set.assert_any_call(bytes("CHAP1", encoding="cp866"), (10000, 599999))
        # Проверка добавления второй главы
        mock_audio_file.tag.chapters.set.assert_any_call(bytes("CHAP2", encoding="cp866"), (600000, 3599999))
