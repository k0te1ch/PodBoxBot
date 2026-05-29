import pytest
from app.utils.validators import validate_path


# Фикстура для пустого файла
@pytest.fixture
def empty_file_path(tmp_path):
    return tmp_path / "test_file.txt"


# Фикстура для существующего файла с содержимым
@pytest.fixture
def existing_file_path_with_content(tmp_path):
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("Existing content", encoding="UTF-8")
    return file_path


# Фикстура для пути к файлу в несуществующей директории
@pytest.fixture
def path_in_nonexistent_directory(tmp_path):
    non_existent_dir = tmp_path / "nonexistent"
    return non_existent_dir / "test_file.txt"


def test_validate_path_creates_file_with_default_encoding(empty_file_path):
    # Проверяем, что файл не существует
    assert not empty_file_path.exists()

    # Вызываем функцию для создания файла с кодировкой по умолчанию (UTF-8)
    validate_path(str(empty_file_path))

    # Проверяем, что файл был создан и пуст
    assert empty_file_path.exists()
    assert empty_file_path.read_text(encoding="UTF-8") == ""


def test_validate_path_creates_file_with_specified_encoding(empty_file_path):
    # Проверяем, что файл не существует
    assert not empty_file_path.exists()

    # Вызываем функцию для создания файла с указанной кодировкой
    validate_path(str(empty_file_path), encoding="ISO-8859-1")

    # Проверяем, что файл был создан и пуст
    assert empty_file_path.exists()
    assert empty_file_path.read_text(encoding="ISO-8859-1") == ""


def test_validate_path_does_not_modify_existing_file(existing_file_path_with_content):
    # Проверяем, что файл существует и содержит текст
    assert existing_file_path_with_content.exists()
    assert existing_file_path_with_content.read_text(encoding="UTF-8") == "Existing content"

    # Вызываем функцию, которая не должна изменять файл
    validate_path(str(existing_file_path_with_content))

    # Проверяем, что содержимое файла не изменилось
    assert existing_file_path_with_content.read_text(encoding="UTF-8") == "Existing content"


def test_validate_path_handles_nonexistent_directory(path_in_nonexistent_directory):
    # Проверяем, что директории и файла еще нет
    assert not path_in_nonexistent_directory.parent.exists()
    assert not path_in_nonexistent_directory.exists()

    # Вызываем функцию, чтобы создать файл в несуществующей директории
    validate_path(str(path_in_nonexistent_directory))

    # Проверяем, что директория и файл были созданы
    assert path_in_nonexistent_directory.exists()
    assert path_in_nonexistent_directory.read_text(encoding="UTF-8") == ""


def test_validate_path_creates_file_in_existing_directory(tmp_path):
    # Создаем существующую директорию, но файл еще не существует
    existing_dir = tmp_path / "existing_directory"
    existing_dir.mkdir()
    file_in_existing_dir = existing_dir / "test_file.txt"

    # Проверяем, что директория существует, но файл еще не создан
    assert existing_dir.exists()
    assert not file_in_existing_dir.exists()

    # Вызываем функцию для создания файла в существующей директории
    validate_path(str(file_in_existing_dir))

    # Проверяем, что файл был создан и пуст
    assert file_in_existing_dir.exists()
    assert file_in_existing_dir.read_text(encoding="UTF-8") == ""
