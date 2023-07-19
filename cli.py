import asyncio
import os
import bot
import click
import importlib
import traceback as tb
from datetime import datetime

from alembic.config import Config
from alembic import command as alembic
from alembic.util.exc import CommandError

from config import DATABASE_URL, SKIP_UPDATES, \
    MODELS_DIR, ENABLE_APSCHEDULER

from loguru import logger


@logger.catch
def get_alembic_conf():
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic_cfg.config_file_name = os.path.join("migrations", 'alembic.ini')
    if os.path.isdir('migrations') is False:
        logger.opt(colors=True).info("<light-blue>Initiating alembic...</light-blue>")
        alembic.init(alembic_cfg, 'migrations')
        with open('migrations/env.py', 'r+') as f:
            content = f.read()
            content = content.replace(
                'target_metadata = None',
                f'from {bot.MAIN_MODULE_NAME} import db\ntarget_metadata = db.metadata')
            f.seek(0)
            f.write(content)

    logger.debug("Alembic is configured")
    return alembic_cfg


@logger.catch
def set_bot_properties():
    loop = bot.executor.asyncio.get_event_loop()
    _ = loop.run_until_complete(bot.bot.get_me())
    for prop, val in _:
        setattr(bot.bot, prop, val)

# CLI COMMANDS
class CliGroup(click.Group):
    def list_commands(self, ctx):
        return [
            "showmigrations",
            "makemigrations",
            "migrate",
            "run"
        ]


@click.group(cls=CliGroup)
def cli():
    pass


@logger.catch
async def _run():
    logger.info("Connecting to Telegram...")

    me = await bot.bot.get_me()
    logger.opt(colors=True).info(f"Bot running as <light-blue>@{me.username}</light-blue>")

    if ENABLE_APSCHEDULER is True:
        bot.scheduler.start()
        logger.success("Scheduler started!")

    logger.success("Bot polling started!")
    await bot.dp.start_polling(bot.bot, skip_updates=SKIP_UPDATES)
    


@cli.command()
@logger.catch
def run():
    asyncio.run(_run())



@logger.catch
@cli.command()
@click.option('--verbose', default=False, is_flag=True)
def showmigrations(verbose):
    cfg = get_alembic_conf()
    history = alembic.history(cfg, verbose=verbose)
    logger.info(history)


@cli.command()
@click.option('-m', '--message', default=None)
def makemigrations(message):
    if message is None:
        logger.opt(colors=True).info("<y>Optinal: User -m <msg, --message=\<msg\> to give a message string to this migrate script</y>")
        message = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    models = [m[:-3] for m in os.listdir(MODELS_DIR) if m.endswith(".py")]
    logger.opt(colors=True).info(f"Loading <y>{len(models)}</y> models")
    for model in models:
        try:
            importlib.import_module(f'{MODELS_DIR}.{model}')
            logger.opt(colors=True).info(f"Loading <y>{model}</y>...   <light-green>loaded</light-green>")
        except ImportError:
            logger.opt(colors=True).exception(f"Loading <y>{model}</y>...   <light-red>error</light-red>")

    try:
        cfg = get_alembic_conf()
        alembic.revision(config=cfg,
                         message=message,
                         autogenerate=True,
                         sql=False,
                         head="head",
                         splice=False,
                         branch_label=None,
                         version_path=None,
                         rev_id=None)
        logger.debug("Alembic revisior")
    except CommandError as err:
        logger.exception("Alembic Command Error")

        if str(err) == "Target database is not up to date.":
            logger.opt(colors=True).info("<y>run \"python bot.py migrate\"</y>")


@logger.catch
@cli.command()
@click.option('-r', '--revision', default="head")
@click.option('--upgrade/--downgrade', default=True, help="Default is upgrade")
def migrate(revision, upgrade):
    cfg = get_alembic_conf()
    if upgrade is True:
        alembic.upgrade(cfg, revision)
        logger.debug("Alembic upgrade")
    else:
        alembic.downgrade(cfg, "-1" if revision == "head" else revision)
        logger.debug("Alembic downgrade")
