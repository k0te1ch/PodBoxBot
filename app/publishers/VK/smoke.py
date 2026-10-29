"""Смоук VK Donut: сессия или токен и тестовый пост. См. SMOKE.md рядом.

docker compose run --rm publisher_vk python smoke.py import-cookie
docker compose run --rm publisher_vk python smoke.py check
docker compose run --rm publisher_vk python smoke.py publish --mp3 /app/files/test.mp3 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from vk_client import VkClient
from vk_podcast import VkPodcastClient, save_session

from shared.config import config


def _client() -> VkClient:
    return VkClient(config.VK_ACCESS_TOKEN, config.VK_GROUP_ID, config.VK_API_VERSION)


def _podcast() -> VkPodcastClient:
    return VkPodcastClient(
        config.VK_SESSION_FILE, config.VK_GROUP_ID, config.VK_PODCAST_PRIVACY, config.VK_PODCAST_COVER_ID
    )


def import_cookie(_args: argparse.Namespace) -> int:
    header = getpass.getpass("Заголовок Cookie запроса к vk.ru (DevTools → Network → Request Headers): ")
    user_agent = input("User-Agent браузера (Enter, чтобы пропустить): ").strip() or None
    count = save_session(config.VK_SESSION_FILE, header, user_agent)
    print(f"Сессия записана в {config.VK_SESSION_FILE} (кук: {count}). Дальше: python smoke.py check")
    return 0


async def check_podcast() -> int:
    client = _podcast()
    try:
        await client.web_token()
        print("сессия vk.ru принята, токен веб-приложения выдан")
        _url, covers = await client.open_add_box()
        print(f"окно добавления эпизода открылось, обложек в галерее: {len(covers)}")
        print(
            f"обложка для эпизода: {client.cover_id or (covers[0] if covers else 'нет, VK поставит обложку подкаста')}"
        )
        print(f"доступ к эпизоду: privacy={client.privacy} (2 — только донам)")
    finally:
        await client.close()
    return 0


async def check(_args: argparse.Namespace) -> int:
    if config.VK_MEDIA == "podcast":
        return await check_podcast()
    client = _client()
    group = await client.get_group()
    print(f"сообщество: {group.get('name')!r} (id {group.get('id')}), админ: {bool(group.get('is_admin'))}")
    print(f"VK Donut: {group.get('donut') or 'нет данных, проверьте, что Donut подключён'}")
    return 0


async def publish(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Публикация настоящего поста для донов: добавьте --yes, если готовы.")
        return 2
    message = f"{args.title}\n\nТестовый пост, будет удалён."
    if config.VK_MEDIA == "podcast":
        podcast = _podcast()
        try:
            post_id = await podcast.publish(args.mp3, title=args.title, desc="смоук", message=message)
            found = bool(await podcast.get_post(post_id))
            print(f"пост: {podcast.post_url(post_id)} (найден через API: {found})")
        finally:
            await podcast.close()
        return 0
    client = _client()
    attachments = []
    if config.VK_MEDIA == "video":
        attachments.append(await client.upload_video(args.mp3, config.VK_COVER_PATH, args.title, "смоук"))
    elif config.VK_MEDIA == "doc":
        attachments.append(await client.upload_doc(args.mp3, "smoke.mp3"))
    post_id = await client.post(message, attachments, -1)
    found = await client.get_post(post_id)
    print(f"пост: {client.post_url(post_id)} (найден через API: {bool(found)}, вложения: {attachments})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Смоук VK-публишера")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-cookie", help="записать сессию vk.ru из заголовка Cookie (режим podcast)")
    sub.add_parser("check", help="проверить сессию или токен и сообщество")
    pub = sub.add_parser("publish", help="опубликовать тестовый пост для донов")
    pub.add_argument("--mp3", required=True)
    pub.add_argument("--title", default="Смоук PodBoxBot")
    pub.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "import-cookie":
        return import_cookie(args)
    return asyncio.run(check(args) if args.command == "check" else publish(args))


if __name__ == "__main__":
    sys.exit(main())
