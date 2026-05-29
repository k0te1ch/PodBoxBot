from unittest.mock import patch

from app.utils.wordpress import WordPress


@patch("app.utils.wordpress.WordPress._load_cookies", return_value=True)
@patch("app.utils.wordpress.WordPress._check_session", return_value=True)
@patch("app.utils.wordpress.WordPress._login")
def test_make_session_with_valid_session(mock_login, mock_check_session, mock_load_cookies, wordpress):
    wordpress._make_session()

    mock_login.assert_not_called()


@patch.object(WordPress, "_login", autospec=True)
@patch.object(WordPress, "_load_cookies", side_effect=lambda: False)
@patch.object(WordPress, "_check_session", side_effect=lambda: False)
def test_make_session_with_invalid_session(mock_check_session, mock_load_cookies, mock_login, wordpress):
    wordpress._make_session()

    mock_login.assert_called_once()
