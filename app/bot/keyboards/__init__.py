from collections.abc import Callable

from .admin import admin_panel_kb, bot_commands_kb, tests_commands_kb

KEYBOARDS: tuple[Callable] = (
    admin_panel_kb,
    bot_commands_kb,
    tests_commands_kb,
)
