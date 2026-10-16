"""Сервисное сообщение по расписанию: поставить, увидеть в очереди, убрать.

Расписание хранится в планировщике бота, поэтому тест разбит на два шага:
``test_schedule_message`` ставит задачу, между шагами бот перезапускают,
``test_scheduled_message_survives_restart`` находит её и удаляет.
"""

import pytest

TEXT = "e2e расписание сервисного сообщения"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_schedule_message(tester, bot_username, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("service")
        await chat.expect(contains=phrase("service_ask_text"))
        await chat.send(TEXT)
        await chat.wait_until(contains=phrase("service_ask_when"), timeout=10)
        await chat.send("когда-нибудь")
        await chat.wait_until(contains=phrase("invalid_service_when"), timeout=10)
        await chat.send("каждую неделю пн 12:00")
        await chat.wait_until(contains="пн в 12:00", timeout=10)
        await chat.click(phrase("de-button-confirm", full=True))
        await chat.wait_until(contains=phrase("service_scheduled"), timeout=10)

        await chat.command("scheduled")
        await chat.expect(contains=TEXT)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scheduled_message_survives_restart(tester, bot_username, phrase):
    async with tester.conversation(bot_username) as chat:
        await chat.command("scheduled")
        await chat.expect(contains=TEXT)
        await chat.click("🗑 1")
        await chat.wait_until(contains=phrase("scheduled_empty"), timeout=10)
