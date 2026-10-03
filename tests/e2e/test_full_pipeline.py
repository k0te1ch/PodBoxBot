"""Full pipeline e2e: /start menu -> "New episode" -> choose type -> upload MP3 -> template ->
FTP/WordPress publish (no chat forwarding).

Buttons are clicked by their text from locales/*.ftl: callback data of the
dialog (DialogEngine) and of the menus (sagenza-tgbot-sdk) is generated.

Menus edit the same message (often the keyboard before answering the
callback): expect_edit and wait_until re-read it, so an edit that landed
before the check is still seen.
"""

from pathlib import Path

import pytest


async def _upload_audio_and_wait_template_prompt(tester, bot_username: str, mp3_path: Path) -> str:
    async with tester.conversation(bot_username, timeout=120) as chat:
        await chat.send_file(str(mp3_path))
        # One message for the whole upload: the reply to the file is edited
        # through the download steps and ends up as the template question.
        await chat.expect()
        template_prompt = await chat.wait_until(contains="Number:", timeout=120)
        return template_prompt.message


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_ftp(tester, bot_username, sample_mp3, episode_template, phrase):
    async with tester.conversation(bot_username) as chat:
        # /start only greets and shows the menu; the upload starts with the button.
        await chat.command("start")
        await chat.expect(contains=phrase("home_admin"), buttons=[phrase("home_new_episode", full=True)])
        await chat.click(phrase("home_new_episode", full=True))
        await chat.wait_until(
            contains=phrase("ask_typeEpisode"),
            buttons=[phrase("main_episode", full=True), phrase("episode_aftershow", full=True)],
            timeout=20,
        )

        # Кнопки диалога inline: выбор типа правит то же сообщение.
        await chat.click(phrase("main_episode", full=True))
        await chat.wait_until(contains=phrase("ask_mp3"), timeout=20)

    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3)

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        # The status message (tags, sending) turns into the audio with the menu.
        await chat.expect()
        await chat.wait_until(
            contains=phrase("done_mp3"),
            buttons=[phrase("audio_ftp", full=True), phrase("audio_site", full=True)],
            timeout=120,
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
        await chat.command("new")
        await chat.expect(contains=phrase("ask_typeEpisode"))
        await chat.click(phrase("main_episode", full=True))
        await chat.wait_until(contains=phrase("ask_mp3"), timeout=20)

    await _upload_audio_and_wait_template_prompt(tester, bot_username, sample_mp3)

    async with tester.conversation(bot_username) as chat:
        await chat.send(episode_template)
        await chat.expect()
        await chat.wait_until(contains=phrase("done_mp3"), timeout=120)

        await chat.click(phrase("audio_site", full=True))
        await chat.expect_edit(buttons=[phrase("wp_upload", full=True)], timeout=10)

        await chat.click(phrase("wp_upload", full=True))
        # Статус сразу правится шагами публишера, поэтому ловим любой текст,
        # а затем итог: в e2e-стенде WordPress направлен в никуда, после всех
        # повторов бот обязан сообщить об ошибке с шагом, а не молчать.
        status = await chat.expect()
        await chat.wait_for_text("ошибка публикации", timeout=240, message=status)
