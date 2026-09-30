"""Смоук Patreon: сессия, правила доступа, HAR редактора, тестовый пост.

    docker compose run --rm publisher_patreon python smoke.py import-cookie
    docker compose run --rm publisher_patreon python smoke.py check
    docker compose run --rm publisher_patreon python smoke.py har /app/data/patreon.har
    docker compose run --rm publisher_patreon python smoke.py publish --mp3 /app/files/test.mp3 --yes

См. SMOKE.md рядом.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from patreon_client import PatreonClient, save_session

from shared.config import config
from shared.publishers.har import summarize


def _client() -> PatreonClient:
    return PatreonClient(config.PATREON_SESSION_FILE, config.PATREON_TIER_IDS)


def import_cookie(_args: argparse.Namespace) -> int:
    session_id = getpass.getpass("Значение куки session_id: ")
    user_agent = input("User-Agent браузера (Enter — пропустить): ").strip() or None
    save_session(config.PATREON_SESSION_FILE, session_id, user_agent)
    print(f"Сессия записана в {config.PATREON_SESSION_FILE}. Дальше: python smoke.py check")
    return 0


def har(args: argparse.Namespace) -> int:
    for line in summarize(args.file, "patreon.com"):
        print(line)
    return 0


async def check(_args: argparse.Namespace) -> int:
    client = _client()
    try:
        print(f"кампания: {await client.ensure_auth()}")
        print(f"правила доступа для поста: {await client.access_rules()}")
    finally:
        await client.close()
    return 0


async def publish(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Публикация настоящего поста для патронов: добавьте --yes, если готовы.")
        return 2
    client = _client()
    try:
        rules = await client.access_rules()
        post_id = await client.create_draft()
        print(f"черновик: {post_id}")
        await client.upload_audio(post_id, args.mp3)
        print("аудио загружено")
        await client.publish(
            post_id, title=args.title, content="<p>Тестовый пост, будет удалён.</p>", teaser="", rule_ids=rules
        )
        print(f"пост: {client.post_url(post_id)} (найден через API: {bool(await client.get_post(post_id))})")
    finally:
        await client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Смоук Patreon-публишера")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-cookie", help="записать сессию из куки браузера")
    sub.add_parser("check", help="проверить сессию и уровни")
    har_cmd = sub.add_parser("har", help="выжимка запросов редактора из HAR")
    har_cmd.add_argument("file")
    pub = sub.add_parser("publish", help="опубликовать тестовый пост")
    pub.add_argument("--mp3", required=True)
    pub.add_argument("--title", default="Смоук PodBoxBot")
    pub.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "import-cookie":
        return import_cookie(args)
    if args.command == "har":
        return har(args)
    return asyncio.run(check(args) if args.command == "check" else publish(args))


if __name__ == "__main__":
    sys.exit(main())
