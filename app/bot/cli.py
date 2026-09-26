import asyncio
import os
from datetime import datetime

import click
from alembic import command as alembic
from alembic.command import revision as alembic_revision
from alembic.config import Config
from alembic.util.exc import CommandError
from loguru import logger

import main
from config import (
    DATABASE_URL,
    ENABLE_APSCHEDULER,
    SKIP_UPDATES,
)
from handlers import COMMANDS
from services.scheduler import init_scheduler_jobs, scheduler


@logger.catch
def get_alembic_conf(sync: bool = False):
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic_cfg.config_file_name = os.path.join("migrations", "alembic.ini")
    if os.path.isdir("migrations") is False:
        logger.opt(colors=True).info("<light-blue>Initiating alembic...</light-blue>")
        alembic.init(alembic_cfg, "migrations", "generic" if sync else "async")
        with open("migrations/env.py", "r+") as f:
            content = f.read()
            content = content.replace(
                "target_metadata = None",
                "from database import db\ntarget_metadata = db.metadata",
            )
            f.seek(0)
            f.write(content)
            f.truncate()

    logger.debug(f"Alembic is configured ({'Sync' if sync else 'Async'})")
    return alembic_cfg


@logger.catch
def set_bot_properties():
    loop = main.executor.asyncio.get_event_loop()
    _ = loop.run_until_complete(main.bot.get_me())
    for prop, val in _:
        setattr(main.bot, prop, val)


# CLI COMMANDS
class CliGroup(click.Group):
    def list_commands(self, ctx):
        return ["showmigrations", "makemigrations", "migrate", "run", "init"]


@click.group(cls=CliGroup)
@click.pass_context
def cli(ctx):
    pass


@logger.catch
async def _run():
    logger.info("Connecting to Telegram...")

    me = await main.bot.get_me()
    logger.opt(colors=True).info(f"Bot running as <light-blue>@{me.username}</light-blue>")

    if ENABLE_APSCHEDULER is True:
        scheduler.start()
        scheduler.remove_all_jobs()
        await init_scheduler_jobs()
        logger.success("Schedulers init jobs configurated and scheduler started!")

    from aiogram.types import BotCommandScopeAllPrivateChats

    # COMMANDS живёт рядом с роутерами (handlers/__init__.py), чтобы список
    # команд и их обработчики правились в одном месте.
    await main.bot.set_my_commands(
        commands=COMMANDS,
        scope=BotCommandScopeAllPrivateChats(),
    )

    logger.success("Bot polling started!")
    await main.dp.start_polling(main.bot, skip_updates=SKIP_UPDATES)


@cli.command()
@logger.catch
def run():
    asyncio.run(_run())


@logger.catch
@cli.command()
@click.option("--verbose", default=False, is_flag=True)
def showmigrations(verbose):
    cfg = get_alembic_conf()
    history = alembic.history(cfg, verbose=verbose)
    logger.info(history)


@cli.command()
@click.option("-m", "--message", default=None)
@click.option("-s", "--sync", default=True)
def makemigrations(message, sync):
    if message is None:
        message = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    try:
        cfg = get_alembic_conf(sync)
        alembic_revision(
            config=cfg,
            message=message,
            autogenerate=True,
            sql=False,
            head="head",
            splice=False,
            branch_label=None,
            version_path=None,
            rev_id=None,
        )
        click.echo("Alembic revision")
    except CommandError as err:
        msg = f"Alembic Command Error: {err}"
        if str(err) == "Target database is not up to date.":
            msg += ' Run "python main.py migrate" first.'
        # ClickException prints to stderr and exits 1. The command used to
        # print the failure and still exit 0, so a failed revision read as
        # success to anything checking the exit code.
        raise click.ClickException(msg) from err


@logger.catch
@cli.command()
@click.option("-r", "--revision", default="head")
@click.option("--upgrade/--downgrade", default=True, help="Default is upgrade")
@click.option("-s", "--sync", default=True)
def migrate(revision, upgrade, sync):
    cfg = get_alembic_conf(sync)
    if upgrade is True:
        alembic.upgrade(cfg, revision)
        logger.debug("Alembic upgrade")
    else:
        alembic.downgrade(cfg, "-1" if revision == "head" else revision)
        logger.debug("Alembic downgrade")
