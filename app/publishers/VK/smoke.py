"""Смоук VK Donut: проверка токена и тестовый пост. См. SMOKE.md рядом.

docker compose run --rm publisher_vk python smoke.py check
docker compose run --rm publisher_vk python smoke.py publish --mp3 /app/files/test.mp3 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from vk_client import VkClient

from shared.config import config


def _client() -> VkClient:
    return VkClient(config.VK_ACCESS_TOKEN, config.VK_GROUP_ID, config.VK_API_VERSION)


async def check(_args: argparse.Namespace) -> int:
    client = _client()
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
    sub.add_parser("check", help="проверить токен и сообщество")
    pub = sub.add_parser("publish", help="опубликовать тестовый пост для донов")
    pub.add_argument("--mp3", required=True)
    pub.add_argument("--title", default="Смоук PodBoxBot")
    pub.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    return asyncio.run(check(args) if args.command == "check" else publish(args))


if __name__ == "__main__":
    sys.exit(main())
