"""Full pipeline e2e: /start -> choose type -> upload MP3 -> template ->
FTP/WordPress publish (no chat forwarding).

The YAML-supported steps go through tgtest's fixtures. The MP3 upload step
is not in tgtest's documented YAML actions, so we drop into Telethon
directly via env vars that tgtest already requires.
"""

import os
from pathlib import Path

import pytest
from telethon import TelegramClient


def _make_client() -> TelegramClient:
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session_name = os.getenv("TG_SESSION", "tgtest_session")
    session_path = Path(__file__).parent / f"{session_name}.session"
    return TelegramClient(str(session_path), api_id, api_hash)


async def _upload_audio_and_wait_template_prompt(bot_username: str, mp3_path: Path) -> str:
    client = _make_client()
    await client.start(phone=lambda: os.environ["TG_PHONE"])
    try:
        async with client.conversation(bot_username, timeout=120) as conv:
            await conv.send_file(str(mp3_path), voice_note=False, attributes=None, force_document=False)
            got = await conv.get_response()
            assert "вижу mp3" in got.message.lower(), f"unexpected: {got.message!r}"
            # the bot edits got_mp3 -> downloaded, then sends ask_template separately
            template_prompt = await conv.get_response()
            return template_prompt.message
    finally:
        await client.disconnect()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_ftp(tester, bot_username, sample_mp3, episode_template):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(contains="что мы добавляем", buttons=["Основной эпизод", "Эпизод послешоу"])

        await chat.click("Основной эпизод")
        await chat.expect(icontains="ожидаю mp3")

    # MP3 upload step — Telethon directly, tgtest doesn't expose file upload.
    await _upload_audio_and_wait_template_prompt(bot_username, sample_mp3)

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        # set_tags -> done_tag -> reply_audio with audio_menu inline keyboard
        await chat.expect(icontains="теги")
        await chat.expect(contains="Вот твой готовый файл", buttons=["FTP", "WordPress"])

        await chat.click(data="FTP_menu")
        await chat.expect_edit(has_buttons=["FTP_upload"])

        await chat.click(data="FTP_upload")
        # popup answer comes back via callback alert; bot also sends "Отправка аудио на FTP"
        await chat.expect(icontains="отправка аудио на ftp")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_wordpress(tester, bot_username, sample_mp3, episode_template):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(contains="что мы добавляем")
        await chat.click("Основной эпизод")
        await chat.expect(icontains="ожидаю mp3")

    await _upload_audio_and_wait_template_prompt(bot_username, sample_mp3)

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        await chat.expect(icontains="теги")
        await chat.expect(contains="Вот твой готовый файл")

        await chat.click(data="WP_menu")
        await chat.expect_edit(has_buttons=["WP_upload"])

        await chat.click(data="WP_upload")
        await chat.expect(icontains="отправка поста на сайт")
