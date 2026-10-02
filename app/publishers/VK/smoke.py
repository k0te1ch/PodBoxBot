"""Смоук VK Donut: вход VK ID, проверка доступа и тестовый пост. См. SMOKE.md.

Режим token (по умолчанию) — статичный VK_ACCESS_TOKEN:
    docker compose run --rm publisher_vk python smoke.py check

Режим vkid — самообновляемая пара токенов VK ID, вход один раз:
    docker compose run --rm publisher_vk python smoke.py authorize   # печатает ссылку
    docker compose run --rm publisher_vk python smoke.py exchange     # обмен кода на токены
    docker compose run --rm publisher_vk python smoke.py check        # чтение без публикации
    docker compose run --rm publisher_vk python smoke.py publish --mp3 /app/files/test.mp3 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import time

import vk_auth
from vk_client import VkClient

from shared.config import config

_DAY = 24 * 3600


def _client() -> VkClient:
    if config.VK_AUTH_MODE == "vkid":
        auth = vk_auth.VkAuth(
            config.VK_CLIENT_ID,
            config.VK_AUTH_FILE,
            client_secret=config.VK_CLIENT_SECRET,
            redirect_uri=config.VK_REDIRECT_URI,
        )
        return VkClient(
            None,
            config.VK_GROUP_ID,
            config.VK_API_VERSION,
            token_provider=auth.access_token,
        )
    return VkClient(config.VK_ACCESS_TOKEN, config.VK_GROUP_ID, config.VK_API_VERSION)


async def authorize(_args: argparse.Namespace) -> int:
    """Печатает ссылку согласия VK ID и code_verifier для последующего обмена."""
    if not config.VK_CLIENT_ID:
        print("Не задан VK_CLIENT_ID приложения VK ID.")
        return 2
    verifier, challenge = vk_auth.make_pkce()
    url = vk_auth.authorize_url(
        config.VK_CLIENT_ID,
        config.VK_REDIRECT_URI,
        challenge,
        "podboxbot",
        config.VK_SCOPE,
    )
    print("1. Откройте ссылку в браузере, где вы вошли администратором сообщества, и нажмите «Разрешить»:")
    print(f"\n{url}\n")
    print("2. Скопируйте из адреса страницы, куда вас перекинет, значения code и device_id.")
    print("3. Запустите `smoke.py exchange` и введите их. code_verifier для этого шага:")
    print(f"\n{verifier}\n")
    return 0


async def exchange(_args: argparse.Namespace) -> int:
    """Обменивает одноразовый код на пару токенов и пишет их в VK_AUTH_FILE."""
    auth = vk_auth.VkAuth(
        config.VK_CLIENT_ID,
        config.VK_AUTH_FILE,
        client_secret=config.VK_CLIENT_SECRET,
        redirect_uri=config.VK_REDIRECT_URI,
    )
    # Скрытый ввод: значения в историю shell и в логи не попадают.
    code = getpass.getpass("code: ").strip()
    device_id = getpass.getpass("device_id: ").strip()
    verifier = getpass.getpass("code_verifier (из authorize): ").strip()
    if not (code and device_id and verifier):
        print("Нужны code, device_id и code_verifier.")
        return 2
    data = await auth.exchange_code(code, device_id, verifier, state="podboxbot")
    left = data.refresh_seconds_left()
    print(f"Готово. Пара токенов записана в {config.VK_AUTH_FILE}.")
    if left:
        print(f"refresh_token действует примерно {left // _DAY} дн., дальше обновляется автоматически.")
    return 0


async def check(_args: argparse.Namespace) -> int:
    """Чтение без публикации: доступ, сообщество, срок токена VK ID."""
    client = _client()
    if config.VK_AUTH_MODE == "vkid":
        auth = vk_auth.VkAuth(
            config.VK_CLIENT_ID,
            config.VK_AUTH_FILE,
            client_secret=config.VK_CLIENT_SECRET,
            redirect_uri=config.VK_REDIRECT_URI,
        )
        status = await auth.status()
        left = status.refresh_seconds_left()
        left_str = f"{left // _DAY} дн." if left is not None else "срок неизвестен"
        access_left = int((status.expires_at or 0) - time.time())
        print(f"режим доступа: VK ID; access истекает через {max(access_left, 0)} с, refresh: {left_str}")
    else:
        print("режим доступа: статичный токен (VK_ACCESS_TOKEN)")
    group = await client.get_group()
    print(f"сообщество: {group.get('name')!r} (id {group.get('id')}), админ: {bool(group.get('is_admin'))}")
    print(f"VK Donut: {group.get('donut') or 'нет данных — проверьте, что Donut подключён'}")
    return 0


async def publish(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Публикация настоящего поста для донов: добавьте --yes, если готовы.")
        return 2
    client = _client()
    attachments = []
    if config.VK_MEDIA == "video":
        attachments.append(await client.upload_video(args.mp3, config.VK_COVER_PATH, args.title, "смоук"))
    elif config.VK_MEDIA == "doc":
        attachments.append(await client.upload_doc(args.mp3, "smoke.mp3"))
    post_id = await client.post(f"{args.title}\n\nТестовый пост, будет удалён.", attachments, -1)
    found = await client.get_post(post_id)
    print(f"пост: {client.post_url(post_id)} (найден через API: {bool(found)}, вложения: {attachments})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Смоук VK-публишера")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("authorize", help="ссылка входа VK ID (режим vkid)")
    sub.add_parser("exchange", help="обмен кода VK ID на пару токенов (режим vkid)")
    sub.add_parser("check", help="проверить доступ и сообщество без публикации")
    pub = sub.add_parser("publish", help="опубликовать тестовый пост для донов")
    pub.add_argument("--mp3", required=True)
    pub.add_argument("--title", default="Смоук PodBoxBot")
    pub.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    handlers = {
        "authorize": authorize,
        "exchange": exchange,
        "check": check,
        "publish": publish,
    }
    return asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
