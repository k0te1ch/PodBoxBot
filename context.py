#TODO welcome
ask_template = {
    "main": "Number: 600\nTitle: Название эпизода\nComment: Описание эпизода\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:28:53 - Название темы 1\n01:40:56 - Название темы 2\n02:17:25 - Озвучили наших патронов и анонсировали послешоу",
    "aftershow": "Number: 600\nTitle: Послешоу. Название эпизода\nComment: Описание эпизода"
}


class ru:
    # Global
    cancel = "Отмена"
    back = "Назад"
    error_occurred = "Произошла ошибка! Пожалуйста, попробуйте снова"
    invalid_input = "Ошибка при вводе!"

    # Start handler
    ask_typeEpisode = "Привет <b>{msg.from_user.first_name}</b>, что мы добавляем?"
    ask_mp3 = "Загружаем <b>{typeEpisode}</b>. Ожидаю mp3"
    got_mp3 = "Вижу MP3, начинаю загрузку"
    done_mp3 = "Вот твой готовый файл!"
    downloaded = "MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:"
    canceled = "Отмененно"

    # Reply keyboard
    main_episode = "Основной эпизод"
    episode_aftershow = "Эпизод послешоу"

    # Admin panel
    admin_panel_open = "Админ панель"
    admin_panel_close = "Админ панель закрыта"
    admin_panel_main = [("Бот", "bot")]
    bot_commands = [("Перезапустить бота", "restart_bot"), ("Выключить бота", "shutdown_bot")]


class en:
    # Global
    cancel = "Cancel"
    back = "Back"
    error_occurred = "An error occurred! please try again"
    invalid_input = "Invalid input!"

    # Start handler
    ask_typeEpisode = "Hello <b>{msg.from_user.first_name}</b>, what are we adding?"
    ask_mp3 = "Loading <b>{typeEpisode}</b>. Waiting for mp3"
    got_mp3 = "I see an MP3, I start downloading"
    done_mp3 = "Here is your finished file!"
    downloaded = "MP3 downloaded! Now came the description of the episode in accordance with the template below, without changing anything except the values of the fields:"
    canceled = "Canceled"

    # Reply keyboard
    main_episode = "Main episode"
    episode_aftershow = "Aftershow episode"

    # Admin panel
    admin_panel_open = "Admin panel"
    admin_panel_close = "Admin panel closed"
    admin_panel_main = [("Bot", "bot")]
    bot_commands = [("Restart the bot", "restart_bot"), ("Turn off the bot", "shutdown_bot")]
