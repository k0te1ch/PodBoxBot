"""Слежение за RSS: разбор ленты, дедупликация, молчаливый первый запуск."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import rss
from services.rss import Episode, RssWatcher, notification_markup, parse_feed

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Test Podcast</title>
  <item>
    <title>Episode 43: Fresh one</title>
    <link>https://example.com/43</link>
    <guid isPermaLink="false">https://example.com/?p=430</guid>
    <description><![CDATA[<p>About &amp; more</p>]]></description>
    <enclosure url="https://example.com/0043_rz_01012026.mp3" length="1" type="audio/mpeg"/>
    <itunes:episode>43</itunes:episode>
  </item>
  <item>
    <title>Aftershow 42</title>
    <link>https://example.com/42-ps</link>
    <guid>https://example.com/?p=421</guid>
    <itunes:episode>42</itunes:episode>
  </item>
  <item><title>No id at all</title></item>
</channel>
</rss>"""


class FakeRedis:
    """Нужные :class:`RssWatcher` команды Redis поверх словаря."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def exists(self, key):
        return int(key in self.values)

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def smembers(self, key):
        return set(self.sets.get(key, set()))


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _watcher(bot, redis) -> RssWatcher:
    return RssWatcher(bot, redis, "https://example.com/feed", [1, 2], interval=600, failure_alert=2)


def test_parse_feed_reads_items():
    episodes = parse_feed(FEED)

    assert [e.guid for e in episodes] == ["https://example.com/?p=430", "https://example.com/?p=421"]
    first, second = episodes
    assert first.number == "43"
    assert first.enclosure_url == "https://example.com/0043_rz_01012026.mp3"
    assert first.description == "About & more"
    assert first.type_episode == "main"
    assert second.number == "42"
    assert second.enclosure_url is None
    # Без mp3 тип не угадываем по названию.
    assert second.type_episode is None


REAL_FEED = Path(__file__).parent / "fixtures" / "podbox_feed.xml"


def test_parse_real_podbox_feed():
    """Обрезанная до трёх выпусков лента https://podbox.ru/feed/podcast/ (2026-09-27)."""
    episodes = parse_feed(REAL_FEED.read_bytes())

    assert [(e.number, e.type_episode) for e in episodes] == [("767", "main"), ("766", "main"), ("5", None)]
    first = episodes[0]
    assert first.title == "767. Послаблений не будет"
    assert first.guid == "9db3862d-1d07-42f4-820a-dedfad1a0dd0"
    assert first.enclosure_url.endswith("/0767_rz_26092026.mp3")
    assert first.link.startswith("https://podbox.ru/")
    # Outcast — другое шоу: mp3 есть, но на площадки его не предлагаем.
    outcast = episodes[2]
    assert outcast.enclosure_url.endswith("/outcast_11092026.mp3")
    assert [
        b.callback_data.split(":")[1] for row in notification_markup(outcast, "ru").inline_keyboard for b in row
    ] == [
        "chat",
        "skip",
    ]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://podbox.ru/podlove/file/1/s/feed/c/podcast/0767_rz_26092026.mp3", ("767", "main")),
        ("https://podbox.ru/files/0123_postshow_01012026.mp3", ("123", "aftershow")),
        ("https://podbox.ru/files/0123_PostShow_01012026.MP3", ("123", "aftershow")),
        ("https://podbox.ru/files/outcast_11092026.mp3", (None, None)),
    ],
)
def test_file_name_decides_type(url, expected):
    xml = f'''<rss><channel><item><title>Послешоу, но нет</title><guid>g</guid>
        <enclosure url="{url}"/></item></channel></rss>'''.encode()

    episode = parse_feed(xml)[0]

    assert (episode.number, episode.type_episode) == expected


def test_markup_hides_prepare_without_mp3():
    with_mp3, without_mp3 = parse_feed(FEED)

    def actions(episode):
        markup = notification_markup(episode, "ru")
        return [b.callback_data.split(":")[1] for row in markup.inline_keyboard for b in row]

    assert actions(with_mp3) == ["chat", "prepare", "skip"]
    assert actions(without_mp3) == ["chat", "skip"]
    assert all(len(b.callback_data) <= 64 for row in notification_markup(with_mp3, "ru").inline_keyboard for b in row)


@pytest.mark.asyncio
async def test_first_run_is_silent_then_only_new_episodes(bot, redis):
    watcher = _watcher(bot, redis)
    old = parse_feed(FEED)

    assert await watcher.process(old) == []

    new = Episode(guid="g-44", title="Episode 44", number="44", type_episode="main")
    fresh = await watcher.process([new, *old])

    assert fresh == [new]
    assert await watcher.process([new, *old]) == []


@pytest.mark.asyncio
async def test_seen_survives_restart(bot, redis):
    await _watcher(bot, redis).process(parse_feed(FEED))

    assert await _watcher(bot, redis).process(parse_feed(FEED)) == []


@pytest.mark.asyncio
async def test_episode_published_by_bot_is_not_offered(bot, redis):
    watcher = _watcher(bot, redis)
    await watcher.process([])
    await rss.mark_published(redis, 44)

    assert await watcher.process([Episode(guid="g-44", title="Episode 44", number="44", type_episode="main")]) == []


@pytest.mark.asyncio
async def test_poll_notifies_every_admin(bot, redis):
    watcher = _watcher(bot, redis)
    await watcher.process([])
    feed_item = parse_feed(FEED)[0]

    with patch.object(watcher, "fetch", AsyncMock(return_value=FEED)):
        fresh = await watcher.poll_once()

    assert [e.guid for e in fresh] == [e.guid for e in parse_feed(FEED)]
    assert bot.send_message.await_count == 4
    assert await rss.load_episode(redis, feed_item.key) == feed_item
    assert "43" in bot.send_message.await_args_list[0].args[1]


@pytest.mark.asyncio
async def test_not_modified_feed_does_nothing(bot, redis):
    watcher = _watcher(bot, redis)
    with patch.object(watcher, "fetch", AsyncMock(return_value=None)):
        assert await watcher.poll_once() == []
    assert not await redis.exists(rss.INITIALIZED_KEY)


@pytest.mark.asyncio
async def test_failures_alert_once(bot, redis):
    watcher = _watcher(bot, redis)
    with patch.object(watcher, "fetch", AsyncMock(side_effect=OSError("down"))):
        for _ in range(4):
            await watcher.tick()

    # failure_alert=2 и два админа: одно предупреждение каждому.
    assert bot.send_message.await_count == 2

    with patch.object(watcher, "fetch", AsyncMock(return_value=None)):
        await watcher.tick()
    assert watcher.failures == 0
