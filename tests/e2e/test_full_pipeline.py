"""Full pipeline e2e: /start -> choose type -> upload MP3 -> template ->
FTP/WordPress publish (no chat forwarding).

The YAML-supported steps go through tgtest's fixtures. The MP3 upload step
is not in tgtest's documented YAML actions, so we drop into Telethon
directly — on tgtest's own connected client: a second client on the same
SQLite session file fails with "database is locked".
"""

import asyncio
from pathlib import Path

import pytest


async def _upload_audio_and_wait_template_prompt(tester, bot_username: str, mp3_path: Path, got_mp3: str) -> str:
    client = tester._client  # tgtest exposes no public accessor for its client
    async with client.conversation(bot_username, timeout=120) as conv:
        await conv.send_file(str(mp3_path), voice_note=False, attributes=None, force_document=False)
        got = await conv.get_response()
        assert got_mp3.lower() in got.message.lower(), f"unexpected: {got.message!r}"
        # the bot edits got_mp3 -> downloaded, then sends ask_template separately
        template_prompt = await conv.get_response()
        return template_prompt.message


async def _open_submenu(tester, chat, data: str, expect_data: str) -> None:
    """Нажать кнопку, которая меняет клавиатуру того же сообщения.

    tgtest's expect_edit races here: the bot edits the markup before answering
    the callback, so the edit event lands before get_edit starts waiting.
    Re-read the message instead and check the new callback data directly.
    """
    await chat.click(data=data)
    msg = chat.last
    buttons: list[str] = []
    for _ in range(20):
        msg = await tester._client.get_messages(msg.chat_id, ids=msg.id)
        buttons = [b.data.decode() for row in (msg.buttons or []) for b in row if b.data]
        if expect_data in buttons:
            chat.last = msg
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"{data}: keyboard never showed {expect_data!r}, got {buttons!r}")


async def _wait_for_text(tester, msg, fragment: str, timeout: float) -> None:
    """Дождаться, пока бот отредактирует сообщение до текста с fragment."""
    text = ""
    for _ in range(int(timeout / 0.5)):
        msg = await tester._client.get_messages(msg.chat_id, ids=msg.id)
        text = msg.text or ""
        if fragment in text:
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"message never contained {fragment!r}, last text: {text!r}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_ftp(tester, bot_username, sample_mp3, episode_template, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(
            contains=phrase("ask_typeEpisode"),
            buttons=[phrase("main_episode", full=True), phrase("episode_aftershow", full=True)],
        )

        await chat.click(phrase("main_episode", full=True))
        await chat.expect(icontains=phrase("ask_mp3"))

    # MP3 upload step — Telethon directly, tgtest doesn't expose file upload.
    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3, phrase("got_mp3"))

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        # set_tags -> done_tag -> reply_audio with audio_menu inline keyboard
        await chat.expect(icontains=phrase("set_tags"))
        await chat.expect(icontains=phrase("done_tag").split("\n")[0])
        await chat.expect(contains=phrase("done_mp3"), buttons=["FTP", "Сайт"])

        await _open_submenu(tester, chat, "FTP_menu", "FTP_upload")

        await chat.click(data="FTP_upload")
        # popup answer comes back via callback alert; bot also sends "Отправка аудио на FTP"
        await chat.expect(icontains="отправка аудио на ftp")
        # The publisher's result comes back through Kafka and edits that message.
        await _wait_for_text(tester, chat.last, "успешно загружен", timeout=120)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_wordpress(tester, bot_username, sample_mp3, episode_template, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(contains=phrase("ask_typeEpisode"))
        await chat.click(phrase("main_episode", full=True))
        await chat.expect(icontains=phrase("ask_mp3"))

    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3, phrase("got_mp3"))

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        await chat.expect(icontains=phrase("set_tags"))
        await chat.expect(icontains=phrase("done_tag").split("\n")[0])
        await chat.expect(contains=phrase("done_mp3"))

        await _open_submenu(tester, chat, "WP_menu", "WP_upload")

        await chat.click(data="WP_upload")
        await chat.expect(icontains="отправка поста на сайт")
