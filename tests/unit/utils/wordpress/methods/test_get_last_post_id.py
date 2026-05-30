from unittest.mock import patch

import pytest


@patch("utils.wordpress.feedparser.parse")
def test_get_last_post_id(mock_feedparser, wordpress):
    mock_feedparser.return_value = {"entries": [{"itunes_episode": "123"}]}

    with pytest.warns(DeprecationWarning, match="get_last_post_ID is deprecated"):
        last_post_id = wordpress.get_last_post_ID()

    assert last_post_id == "123"
    mock_feedparser.assert_called_once()
