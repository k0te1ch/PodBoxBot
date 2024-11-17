import pytest
from unittest import mock
from pathlib import Path
from app.utils.bot_methods import get_zip_logs

def create_mock_file(name, is_file) -> mock.Mock:
    file = mock.Mock(spec=Path)
    file.is_file.return_value = is_file
    file.name = name
    file.__lt__ = lambda self, other: self.name < other.name
    return file


@pytest.fixture
def mock_paths():
    """Фикстура для мока глобальных переменных путей"""
    with (
        mock.patch("app.utils.bot_methods.FILES_PATH", Path("/mocked/files_path")),
        mock.patch("app.utils.bot_methods.LOGS_PATH", Path("/mocked/logs_path")),
    ):
        yield


@pytest.fixture
def mock_log_files():
    """Фикстура для мока файлов логов"""

    return create_mock_file("log1.log", True), create_mock_file("log2.log", True)


@pytest.fixture
def mock_non_file():
    """Фикстура для мока объекта, который не является файлом"""
    
    return create_mock_file("not_a_file", False)


@mock.patch("pathlib.Path.glob")
@mock.patch("zipfile.ZipFile")
def test_get_zip_logs(mock_zipfile, mock_glob, mock_paths, mock_log_files):
    """Тестирование успешного создания ZIP архива с логами"""
    log1, log2 = mock_log_files
    mock_glob.return_value = [log1, log2]

    log_name = "test_logs.zip"
    result = get_zip_logs(log_name)

    # Проверяем путь создаваемого архива
    assert result == Path("/mocked/files_path/test_logs.zip")

    # Проверяем, что ZipFile был вызван
    mock_zipfile.assert_called_once_with(Path("/mocked/files_path/test_logs.zip"), mode="w")

    # Проверяем, что в архив были добавлены файлы
    mock_zip = mock_zipfile.return_value.__enter__.return_value
    mock_zip.write.assert_any_call(log1, arcname="logs/log1.log")
    mock_zip.write.assert_any_call(log2, arcname="logs/log2.log")


@mock.patch("pathlib.Path.glob")
@mock.patch("zipfile.ZipFile")
def test_get_zip_logs_no_logs(mock_zipfile, mock_glob, mock_paths):
    """Тестирование, когда нет лог файлов"""
    mock_glob.return_value = []

    log_name = "test_logs.zip"
    result = get_zip_logs(log_name)

    # Проверяем, что None возвращается, когда нет логов
    assert result is None

    # Проверяем, что архив не был создан
    mock_zipfile.assert_not_called()


@mock.patch("pathlib.Path.glob")
@mock.patch("zipfile.ZipFile")
def test_get_zip_logs_with_non_files(mock_zipfile, mock_glob, mock_paths, mock_log_files, mock_non_file):
    """Тестирование, когда логи не являются файлами (директории или другие объекты)"""
    log1, log2 = mock_log_files
    not_a_file = mock_non_file
    mock_glob.return_value = [log1, log2, not_a_file]

    log_name = "test_logs.zip"
    result = get_zip_logs(log_name)

    # Проверяем путь создаваемого архива
    assert result == Path("/mocked/files_path/test_logs.zip")

    # Проверяем, что ZipFile был вызван
    mock_zipfile.assert_called_once_with(Path("/mocked/files_path/test_logs.zip"), mode="w")

    # Проверяем, что только настоящие файлы были добавлены
    mock_zip = mock_zipfile.return_value.__enter__.return_value
    mock_zip.write.assert_any_call(log1, arcname="logs/log1.log")
    mock_zip.write.assert_any_call(log2, arcname="logs/log2.log")

    # Проверяем, что "/mocked/logs_path/not_a_file" не был вызван
    assert not any(call[0][0] == not_a_file for call in mock_zip.write.call_args_list)


@mock.patch("pathlib.Path.glob")
@mock.patch("zipfile.ZipFile")
def test_get_zip_logs_empty_log_name(mock_zipfile, mock_glob, mock_paths, mock_log_files):
    """Тестирование, когда передается пустое имя лога"""
    log1, _ = mock_log_files
    mock_glob.return_value = [log1]

    log_name = ""
    result = get_zip_logs(log_name)

    # Проверяем, что ZIP файл был создан с пустым именем
    assert result == Path("/mocked/files_path/")

    # Проверяем, что ZipFile был вызван
    mock_zipfile.assert_called_once_with(Path("/mocked/files_path/"), mode="w")

    # Проверяем, что файл был добавлен в архив
    mock_zip = mock_zipfile.return_value.__enter__.return_value
    mock_zip.write.assert_called_once_with(log1, arcname="logs/log1.log")


@mock.patch("zipfile.ZipFile", side_effect=Exception("Test exception"))
@mock.patch("pathlib.Path.glob")
def test_get_zip_logs_error_logging(mock_glob, mock_zipfile, mock_paths, caplog):
    """Тестирование логирования ошибок при создании ZIP архива"""
    # Мокаем наличие одного файла лога
    log_file = mock.Mock(spec=Path)
    log_file.is_file.return_value = True
    log_file.name = "log1.log"
    mock_glob.return_value = [log_file]

    log_name = "test_logs.zip"

    # Запускаем функцию, которая вызовет исключение
    with caplog.at_level("ERROR"):
        result = get_zip_logs(log_name)

    # Проверка, что функция вернула None из-за исключения
    assert result is None

    # Проверка, что сообщение об ошибке было записано в лог
    assert any(
        "Error occurred while creating the log archive: Test exception" in message for message in caplog.messages
    ), "Expected error message not found in logs"
