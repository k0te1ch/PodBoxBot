"""Смоук Boosty на живом блоге — запускает владелец, когда есть свежий логин.

Все команды работают внутри контейнера publisher_boosty (там конфиг и том
secrets/boosty смонтирован в /app/data)::

    docker compose run --rm publisher_boosty python smoke.py import-cookie
    docker compose run --rm publisher_boosty python smoke.py check
    docker compose run --rm publisher_boosty python smoke.py publish --mp3 /app/files/test.mp3 --yes

* ``import-cookie`` — спрашивает значения кук ``auth`` и ``_clientId`` и пишет
  auth.json (значения читаются из stdin, в историю shell не попадают);
* ``check`` — грузит токены, делает refresh, читает блог и уровни подписки,
  ничего не публикует;
* ``publish`` — настоящая публикация тестового поста тем же кодом, что и
  publisher. Без ``--yes`` не запускается: пост увидят платные подписчики.

Подробности — в SMOKE.md рядом.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from boosty_auth import AuthData, save
from boosty_client import BoostyClient

from shared.config import config


def _client() -> BoostyClient:
    return BoostyClient(config.BOOSTY_BLOG or "", config.BOOSTY_AUTH_FILE)


def import_cookie(_args: argparse.Namespace) -> int:
    auth_cookie = getpass.getpass("Значение куки auth: ")
    client_id = getpass.getpass("Значение куки _clientId: ")
    user_agent = input("User-Agent браузера (Enter — по умолчанию): ").strip() or None
    data = AuthData.from_cookies(auth_cookie, client_id, user_agent)
    Path(config.BOOSTY_AUTH_FILE).parent.mkdir(parents=True, exist_ok=True)
    save(config.BOOSTY_AUTH_FILE, data)
    print(f"Токены записаны в {config.BOOSTY_AUTH_FILE}. Дальше: python smoke.py check")
    return 0


async def check(_args: argparse.Namespace) -> int:
    client = _client()
    try:
        await client.ensure_auth()
        await client.refresh()
        print("refresh: ok")
        blog = await client.get_blog()
        owner = blog.get("owner") if isinstance(blog.get("owner"), dict) else {}
        print(f"блог: {blog.get('title')!r}, ownerId: {owner.get('id') or blog.get('ownerId')}")
        for level in await client.get_subscription_levels():
            print(f"уровень: id={level.get('id')} name={level.get('name')!r} price={level.get('price')}")
        if not config.BOOSTY_SUBSCRIPTION_LEVEL_ID:
            print("BOOSTY_SUBSCRIPTION_LEVEL_ID не задан — возьмите id платного уровня из списка выше")
        if not config.BOOSTY_OWNER_ID:
            print("BOOSTY_OWNER_ID не задан — укажите ownerId из строки блога")
    finally:
        await client.close()
    return 0


async def publish(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Публикация настоящего поста: добавьте --yes, если готовы.")
        return 2
    if not config.BOOSTY_SUBSCRIPTION_LEVEL_ID or not config.BOOSTY_OWNER_ID:
        print("Сначала заполните BOOSTY_SUBSCRIPTION_LEVEL_ID и BOOSTY_OWNER_ID (см. check).")
        return 2
    client = _client()
    try:
        audio_id, size = await client.upload_audio(args.mp3, config.BOOSTY_OWNER_ID)
        print(f"аудио: {audio_id} ({size} байт)")
        cover_id = await client.upload_image(config.BOOSTY_COVER_PATH)
        print(f"обложка: {cover_id}")
        post_id = await client.publish(
            title=args.title,
            body="Тестовый пост смоука PodBoxBot, будет удалён.",
            chapters=[["00:00", "Начало"]],
            audio_id=audio_id,
            audio_size=size,
            audio_title=Path(args.mp3).name,
            cover_id=cover_id,
            subscription_level_id=config.BOOSTY_SUBSCRIPTION_LEVEL_ID,
            price=config.BOOSTY_PRICE,
            advertiser_info=config.BOOSTY_ADVERTISER_INFO,
        )
        post = await client.get_post(post_id)
        print(f"пост: https://boosty.to/{config.BOOSTY_BLOG}/posts/{post_id} (найден через API: {bool(post)})")
    finally:
        await client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Смоук Boosty-публишера")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-cookie", help="записать auth.json из кук браузера")
    sub.add_parser("check", help="проверить токены и блог без публикации")
    pub = sub.add_parser("publish", help="опубликовать тестовый пост")
    pub.add_argument("--mp3", required=True, help="короткий mp3 внутри контейнера")
    pub.add_argument("--title", default="Смоук PodBoxBot")
    pub.add_argument("--yes", action="store_true", help="подтверждаю публикацию")
    args = parser.parse_args(argv)

    if args.command == "import-cookie":
        return import_cookie(args)
    runner = check if args.command == "check" else publish
    return asyncio.run(runner(args))


if __name__ == "__main__":
    sys.exit(main())
