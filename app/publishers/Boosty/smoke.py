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
  publisher. Без ``--yes`` не запускается: пост увидят платные подписчики;
* ``schedule`` — отложенный пост на год вперёд с меткой ``[e2e-test ...]``:
  создаёт, проверяет ``isPublished=false``, удаляет и проверяет удаление.
  Если Boosty опубликовал пост сразу, удаляет его и выходит с кодом 3.

Подробности — в SMOKE.md рядом.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import time
from datetime import datetime
from pathlib import Path

from boosty_auth import AuthData, save
from boosty_client import BoostyApiError, BoostyClient, BoostyPublishedNowError, PostContent

from shared.config import config

# Отложенный пост смоука выходит не раньше чем через год: успеть удалить с запасом.
SCHEDULE_AHEAD = 366 * 24 * 3600


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
        post_id = await client.publish(await _test_post(client, args.mp3, args.title))
        post = await client.get_post(post_id)
        print(f"пост: https://boosty.to/{config.BOOSTY_BLOG}/posts/{post_id} (найден через API: {bool(post)})")
    finally:
        await client.close()
    return 0


async def _test_post(client: BoostyClient, mp3: str, title: str) -> PostContent:
    audio_id, size = await client.upload_audio(mp3, config.BOOSTY_OWNER_ID)
    print(f"аудио: {audio_id} ({size} байт)")
    cover_id = await client.upload_image(config.BOOSTY_COVER_PATH)
    print(f"обложка: {cover_id}")
    return PostContent(
        title=title,
        body="Тестовый пост смоука PodBoxBot, будет удалён.",
        chapters=[["00:00", "Начало"]],
        audio_id=audio_id,
        audio_size=size,
        audio_title=Path(mp3).name,
        cover_id=cover_id,
        subscription_level_id=config.BOOSTY_SUBSCRIPTION_LEVEL_ID,
        price=config.BOOSTY_PRICE,
        advertiser_info=config.BOOSTY_ADVERTISER_INFO,
    )


async def schedule(args: argparse.Namespace) -> int:
    """Отложенный пост на год вперёд: создать, проверить, удалить, проверить удаление."""
    if not config.BOOSTY_SUBSCRIPTION_LEVEL_ID or not config.BOOSTY_OWNER_ID:
        print("Сначала заполните BOOSTY_SUBSCRIPTION_LEVEL_ID и BOOSTY_OWNER_ID (см. check).")
        return 2
    title = f"[e2e-test {datetime.now():%Y%m%d-%H%M}] {args.title}"
    publish_time = int(time.time()) + SCHEDULE_AHEAD
    client = _client()
    try:
        post = await _test_post(client, args.mp3, title)
        try:
            scheduled = await client.schedule(post, publish_time, showcase=False)
        except BoostyPublishedNowError as e:
            # Пост ушёл подписчикам: удалить сразу и громко сообщить.
            if e.post_id:
                await client.delete_post(e.post_id)
            print(f"ОПУБЛИКОВАН СРАЗУ, пост {e.post_id or '?'} удалён. Проверьте блог и уведомления.")
            return 3
        post_id = str(scheduled.get("id") or "")
        print(f"отложенный пост: {post_id} (isPublished={scheduled.get('isPublished')})")
        fetched = await client.get_post(post_id)
        print(f"через API: isPublished={fetched.get('isPublished')}, publishTime={fetched.get('publishTime')}")
        await client.delete_post(post_id)
        print(f"удалён: {post_id}")
        try:
            gone = await client.get_post(post_id)
        except BoostyApiError as e:
            print(f"проверка удаления: HTTP {e.status}")
        else:
            print(f"проверка удаления: isDeleted={gone.get('isDeleted')}")
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
    sch = sub.add_parser("schedule", help="отложенный пост на год вперёд, сразу удаляется")
    sch.add_argument("--mp3", required=True, help="короткий mp3 внутри контейнера")
    sch.add_argument("--title", default="Смоук PodBoxBot")
    args = parser.parse_args(argv)

    if args.command == "import-cookie":
        return import_cookie(args)
    runners = {"check": check, "publish": publish, "schedule": schedule}
    return asyncio.run(runners[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
