import pytest
from unittest.mock import patch

from app.utils.wordpress import WordPress


def test_enter_method():
    wp = WordPress()
    with wp as entered_wp:
        # Проверяем, что объект возвращается самим собой
        assert entered_wp is wp
