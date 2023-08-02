#TODO welcome
ask_template: dict = {
    "main":
    "Number: 600\nTitle: Название эпизода\nComment: Описание эпизода\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:28:53 - Название темы 1\n01:40:56 - Название темы 2\n02:17:25 - Озвучили наших патронов и анонсировали послешоу",
    "aftershow":
    "Number: 600\nTitle: Послешоу. Название эпизода\nComment: Описание эпизода"
}


class ru:
    # Global
    cancel: str = "Отмена"
    back: str = "Назад"
    error_occurred: str = "Произошла ошибка! Пожалуйста, попробуйте снова"
    invalid_input: str = "Ошибка при вводе!"

    # Start handler
    ask_typeEpisode: str = "Привет <b>{msg.from_user.first_name}</b>, что мы добавляем?"
    ask_mp3: str = "Загружаем <b>{typeEpisode}</b>. Ожидаю mp3"
    got_mp3: str = "Вижу MP3, начинаю загрузку"
    done_mp3: str = "Вот твой готовый файл!"
    set_tags: str = "Проставляем теги"
    downloaded: str = "MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:"
    done_tag: str = "Теги проставлены.\nЗагрузка началась, подождите около 2-5 минут"
    canceled: str = "Отмененно"

    # Reply keyboard
    main_episode: str = "Основной эпизод"
    episode_aftershow: str = "Эпизод послешоу"

    # Admin panel
    admin_panel_open: str = "Админ панель"
    admin_panel_close: str = "Админ панель закрыта"
    admin_panel_main: list = [("Бот", "bot")]
    bot_commands: list = [("Выключить бота", "shutdown_bot")]


class en:
    # Global
    cancel: str = "Cancel"
    back: str = "Back"
    error_occurred: str = "An error occurred! please try again"
    invalid_input: str = "Invalid input!"

    # Start handler
    ask_typeEpisode: str = "Hello <b>{msg.from_user.first_name}</b>, what are we adding?"
    ask_mp3: str = "Loading <b>{typeEpisode}</b>. Waiting for mp3"
    got_mp3: str = "I see an MP3, I start downloading"
    done_mp3: str = "Here is your finished file!"
    done_tag: str = "" #TODO Translate
    downloaded: str = "MP3 downloaded! Now came the description of the episode in accordance with the template below, without changing anything except the values of the fields:"
    canceled: str = "Canceled"

    # Reply keyboard
    main_episode: str = "Main episode"
    episode_aftershow: str = "Aftershow episode"

    # Admin panel
    admin_panel_open: str = "Admin panel"
    admin_panel_close: str = "Admin panel closed"
    admin_panel_main: list = [("Bot", "bot")]
    bot_commands: list = [("Turn off the bot", "shutdown_bot")]
