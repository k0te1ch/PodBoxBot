import pytest

from config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@my_group", "@my_group"),
        ("my_group", "@my_group"),
        ("  my_group ", "@my_group"),
        # A private group has no username, its numeric id must stay an id.
        ("-1001234567890", "-1001234567890"),
        (" -1001234567890 ", "-1001234567890"),
        ("123456789", "123456789"),
    ],
)
def test_forward_chat_accepts_a_username_or_a_numeric_id(monkeypatch, raw, expected):
    monkeypatch.setenv("FORWARD_CHAT_USERNAME", raw)

    chat = Settings(_env_file=None).FORWARD_CHAT_USERNAME

    assert chat == expected
