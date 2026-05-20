from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    PeerIdInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.types import Channel


@logger.catch
async def join_to_private_channel(client: TelegramClient, channel_name: str) -> bool:
    """
    Joins a public Telegram channel by its name

    :param client: The `TelegramClient` instance
    :param channel_name: The name or username of the public channel to join
    :return: True if successfully joined, False if an error occurred
    """
    try:
        # Пробуем присоединиться к каналу
        await client(JoinChannelRequest(channel_name))
        logger.info(f"Successfully joined the channel: {channel_name}")
        return True

    except ChannelPrivateError:
        logger.error(f"Channel '{channel_name}' is private or requires an invite")
    except UserAlreadyParticipantError:
        logger.warning(f"Already a member of the channel '{channel_name}'")
    except PeerIdInvalidError:
        logger.error(f"Invalid channel name '{channel_name}' or channel does not exist")
    except Exception as e:
        logger.error(f"An unexpected error occurred while joining channel '{channel_name}': {e}")

    return False


@logger.catch
async def join_to_public_channel(client: TelegramClient, channel_name: str) -> bool:
    """
    Joins a public Telegram channel by its name

    :param client: The `TelegramClient` instance
    :param channel_name: The name or username of the public channel to join
    :return: True if successfully joined, False if an error occurred
    """
    try:
        # Пробуем присоединиться к каналу
        await client(JoinChannelRequest(channel_name))
        logger.info(f"Successfully joined the channel: {channel_name}")
        return True

    except ChannelPrivateError:
        logger.error(f"Channel '{channel_name}' is private or requires an invite")
    except UserAlreadyParticipantError:
        logger.warning(f"Already a member of the channel '{channel_name}'")
    except PeerIdInvalidError:
        logger.error(f"Invalid channel name '{channel_name}' or channel does not exist")
    except Exception as e:
        logger.error(f"An unexpected error occurred while joining channel '{channel_name}': {e}")

    return False


@logger.catch
async def get_channel_info(client: TelegramClient, channel_name: str) -> dict | None:
    """
    Retrieves information about a public Telegram channel (e.g., channel ID, joinability)

    :param client: The `TelegramClient` instance
    :param channel_name: The name or username of the channel
    :return: A dictionary with channel information or None if an error occurred
    """
    try:
        # Получаем полную информацию о канале
        full_channel = await client(GetFullChannelRequest(channel_name))

        # Проверяем, что это канал и извлекаем информацию
        if isinstance(full_channel.chats[0], Channel):
            channel = full_channel.chats[0]
            channel_id = channel.id
            is_joined = True
            if not channel.username and channel.usernames:
                username = channel.usernames[0].username
            else:
                username = channel.username

            slug = f"@{username}"
            link = f"t.me/{username}"
            channel_name = channel.title

            logger.info(
                f"Channel ID: {channel_id}, Can join: {is_joined}, Channel name: {channel_name}, Slug: {slug}, Link: {link}"
            )

            return {
                "channel_id": channel_id,
                "can_join": is_joined,
                "name": channel_name,
                "slug": slug,
                "link": link,
            }

        # Если объект не является каналом, возвращаем None
        logger.error(f"Channel '{channel_name}' is not a valid channel")
        return None

    except ChannelPrivateError:
        logger.error(f"Channel '{channel_name}' is private or requires an invite")
    except PeerIdInvalidError:
        logger.error(f"Invalid channel name '{channel_name}' or channel does not exist")
    except Exception as e:
        logger.error(f"An unexpected error occurred while retrieving info for channel '{channel_name}': {e}")

    return None


@logger.catch
async def is_user_in_channel(client: TelegramClient, channel: str) -> bool:
    """
    Checks if the user is a member of the specified channel

    :param client: The `TelegramClient` instance
    :param channel The username or link of the channel
    :return: True if the user is a member, False otherwise
    """
    try:
        channel_entity = await client.get_entity(channel)

        if not isinstance(channel_entity, Channel):
            logger.warning(f"The provided entity is not a channel: {channel}")
            return False

        async for dialog in client.iter_dialogs():
            if dialog.entity.username == channel_entity.username:
                logger.info(f"User is a member of the channel: {channel}")
                return True

        logger.info(f"User is not a member of the channel: {channel}")
        return False

    except Exception as e:
        logger.error(f"An error occurred while checking if the user is in channel '{channel}': {e}")
        return False
