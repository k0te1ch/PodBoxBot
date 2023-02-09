import os
import pytest
from src import settings

@pytest.fixture(scope="function", autouse=True)
def configuration_setup(request):
    settings.PATH = "test_settings.ini"
    settings.FIELDS = ["token", "font", "font_size", "font_info"]
    settings.SETTINGS = settings.Config().getInfo()
    def configuration_teardown():
        os.remove("test_settings.ini")
    request.addfinalizer(configuration_teardown)


def test_not_found_config():
    os.remove("test_settings.ini")
    settings.Config().getInfo()

    assert os.path.exists(settings.PATH)

def test_not_correct_config():
    SETTINGS = settings.SETTINGS
    os.remove("test_settings.ini")
    settings.FIELDS.pop()
    settings.SETTINGS = settings.Config().getInfo()

    assert SETTINGS != settings.SETTINGS

#TODO Доделать тест
def test_not_correct_type_config():

    assert SETTINGS != settings.SETTINGS

#TODO Придумать ещё тестов