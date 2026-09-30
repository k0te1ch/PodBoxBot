"""Full pipeline e2e: /start -> choose type -> upload MP3 -> template ->
FTP/WordPress publish (no chat forwarding).

Buttons are clicked by their text from locales/*.ftl: callback data of the
dialog (DialogEngine) and of the menus (sagenza-tgbot-sdk) is generated.

Menus edit the same message (often the keyboard before answering the
callback): expect_edit and wait_until re-read it, so an edit that landed
before the check is still seen.
"""

from pathlib import Path

import pytest


async def _upload_audio_and_wait_template_prompt(tester, bot_username: str, mp3_path: Path, got_mp3: str) -> str:
    async with tester.conversation(bot_username, timeout=120) as chat:
        await chat.send_file(str(mp3_path))
        await chat.expect(icontains=got_mp3)
        # the bot edits got_mp3 -> downloaded, then sends ask_template separately
        template_prompt = await chat.get_reply()
        return template_prompt.message


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_ftp(tester, bot_username, sample_mp3, episode_template, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(
            contains=phrase("ask_typeEpisode"),
            buttons=[phrase("main_episode", full=True), phrase("episode_aftershow", full=True)],
        )

        # Кнопки диалога inline: выбор типа правит то же сообщение.
        await chat.click(phrase("main_episode", full=True))
        await chat.wait_until(contains=phrase("ask_mp3"), timeout=20)

    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3, phrase("got_mp3"))

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        # set_tags -> done_tag -> reply_audio with audio_menu inline keyboard
        await chat.expect(icontains=phrase("set_tags"))
        await chat.expect(icontains=phrase("done_tag").split("\n")[0])
        await chat.expect(
            contains=phrase("done_mp3"),
            buttons=[phrase("audio_ftp", full=True), phrase("audio_site", full=True)],
        )

        await chat.click(phrase("audio_ftp", full=True))
        await chat.expect_edit(buttons=[phrase("ftp_upload", full=True)], timeout=10)

        await chat.click(phrase("ftp_upload", full=True))
        # Статус-сообщение правится прогрессом публишера, ловим любой текст
        # и ждём итога, который приходит через Kafka.
        status = await chat.expect()
        await chat.wait_for_text("успешно загружен", timeout=120, message=status)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_wordpress(tester, bot_username, sample_mp3, episode_template, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("start")
        await chat.expect(contains=phrase("ask_typeEpisode"))
        await chat.click(phrase("main_episode", full=True))
        await chat.wait_until(contains=phrase("ask_mp3"), timeout=20)

    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3, phrase("got_mp3"))

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        await chat.expect(icontains=phrase("set_tags"))
        await chat.expect(icontains=phrase("done_tag").split("\n")[0])
        await chat.expect(contains=phrase("done_mp3"))

        await chat.click(phrase("audio_site", full=True))
        await chat.expect_edit(buttons=[phrase("wp_upload", full=True)], timeout=10)

        await chat.click(phrase("wp_upload", full=True))
        # Статус сразу правится шагами публишера, поэтому ловим любой текст,
        # а затем итог: в e2e-стенде WordPress направлен в никуда, после всех
        # повторов бот обязан сообщить об ошибке с шагом, а не молчать.
        status = await chat.expect()
        await chat.wait_for_text("ошибка публикации", timeout=240, message=status)
