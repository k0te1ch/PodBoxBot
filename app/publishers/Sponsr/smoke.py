"""Смоук Sponsr: сессия и выжимка HAR редактора. См. SMOKE.md рядом.

docker compose run --rm publisher_sponsr python smoke.py import-cookie
docker compose run --rm publisher_sponsr python smoke.py check
docker compose run --rm publisher_sponsr python smoke.py har /app/data/sponsr.har
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sponsr_client import SponsrClient, save_session

from shared.config import config
from shared.publishers.har import summarize


def import_cookie(_args: argparse.Namespace) -> int:
    sess = getpass.getpass("Значение куки SESS: ")
    user_agent = input("User-Agent браузера (Enter — пропустить): ").strip() or None
    save_session(config.SPONSR_SESSION_FILE, sess, user_agent)
    print(f"Сессия записана в {config.SPONSR_SESSION_FILE}. Дальше: python smoke.py check")
    return 0


def har(args: argparse.Namespace) -> int:
    for line in summarize(args.file, "sponsr.ru"):
        print(line)
    return 0


async def check(_args: argparse.Namespace) -> int:
    client = SponsrClient(config.SPONSR_SESSION_FILE, config.SPONSR_PROJECT)
    try:
        await client.ensure_auth()
        print(f"сессия принята, проект: {client.post_url('').rstrip('/')}")
    finally:
        await client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Смоук Sponsr-публишера")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-cookie", help="записать сессию из куки браузера")
    sub.add_parser("check", help="проверить сессию")
    har_cmd = sub.add_parser("har", help="выжимка запросов редактора из HAR")
    har_cmd.add_argument("file")
    args = parser.parse_args(argv)

    if args.command == "import-cookie":
        return import_cookie(args)
    if args.command == "har":
        return har(args)
    return asyncio.run(check(args))


if __name__ == "__main__":
    sys.exit(main())
