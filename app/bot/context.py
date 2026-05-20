ask_template: dict = {
    "main": '<pre language="text">Number: 600\nTitle: Название эпизода\nComment: Описание эпизода\nTags: Окно, жесть, спина\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:28:53 - Название темы 1\n01:40:56 - Название темы 2\n02:17:25 - Озвучили наших патронов и анонсировали послешоу</pre>',
    "aftershow": '<pre language="text">Number: 600\nTitle: Послешоу. Название эпизода\nComment: Описание эпизода</pre>',
}

# TODO: welcome


class ru:
    # Global
    cancel: str = "Отмена"
    back: str = "Назад"
    error_occurred: str = "Произошла ошибка! Пожалуйста, попробуйте снова"
    invalid_input: str = "Ошибка при вводе!"

    # Start handler
    ask_typeEpisode: str = "Привет <b>{msg.from_user.first_name}</b>, что мы добавляем?"
    ask_mp3: str = "Загружаем <u><b>{type_episode_text}</b></u>. Ожидаю MP3 файл"
    got_mp3: str = "Вижу MP3, начинаю загрузку"
    done_mp3: str = "Вот твой готовый файл!"
    set_tags: str = "Проставляем теги"
    downloaded: str = "MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:"
    done_tag: str = "Теги проставлены.\nЗагрузка началась, подождите около 2-5 минут"
    canceled: str = "Отменено"

    # Reply keyboard
    main_episode: str = "Основной эпизод"
    episode_aftershow: str = "Эпизод послешоу"

    # Admin panel
    admin_panel_open: str = "Админ панель"
    admin_panel_close: str = "Админ панель закрыта"
    admin_panel_main: list = [("Бот", "botPanel")]  # noqa: RUF012
    bot_commands: list = [  # noqa: RUF012
        ("Выключить бота", "shutdown_bot"),
        ("Прислать лог-файлы", "send_logs"),
    ]


class en:
    # Global
    cancel: str = "Cancel"
    back: str = "Back"
    error_occurred: str = "An error occurred! please try again"
    invalid_input: str = "Invalid input!"

    # Start handler
    ask_typeEpisode: str = "Hello <b>{msg.from_user.first_name}</b>, what are we adding?"
    ask_mp3: str = "Loading <u><b>{type_episode}</b></u>. Waiting for MP3 file"
    got_mp3: str = "I see an MP3, I start downloading"
    done_mp3: str = "Here is your finished file!"
    done_tag: str = "The tags are attached.\nThe download has started, wait about 2-5 minutes"
    downloaded: str = "MP3 downloaded! Now came the description of the episode in accordance with the template below, without changing anything except the values of the fields:"
    canceled: str = "Canceled"

    # Reply keyboard
    main_episode: str = "Main episode"
    episode_aftershow: str = "Aftershow episode"

    # Admin panel
    admin_panel_open: str = "Admin panel"
    admin_panel_close: str = "Admin panel closed"
    admin_panel_main: list = [("Bot", "bot")]  # noqa: RUF012
    bot_commands: list = [  # noqa: RUF012
        ("Turn off the bot", "shutdown_bot"),
        ("Send log files", "send_logs"),
    ]


class AdminPanel:
    opened = "Админ панель"

    panels: list = [("Бот", "bot_panel"), ("Тесты", "tests_panel")]  # noqa: RUF012

    bot_commands: list = [  # noqa: RUF012
        ("Выключить бота", "shutdown_bot"),
        ("Перезагрузить бота", "restart_bot"),
        ("Прислать лог-файлы", "send_logs"),
        ("Назад", "admin_back"),
    ]

    test_news_commands: list = [  # noqa: RUF012
        ("Назад", "admin_back"),
    ]
