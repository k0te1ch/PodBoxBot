cancel = Отмена
back = Назад
error_occurred = Произошла ошибка! Пожалуйста, попробуйте снова
invalid_input = Ошибка при вводе!
download_failed = ❌ MP3 не загружен. Проверь файл и попробуй ещё раз.

ask_typeEpisode = Привет <b>{msg.from_user.first_name}</b>, что мы добавляем?
ask_mp3 = Загружаем <u><b>{type_episode_text}</b></u>. Ожидаю MP3 файл
got_mp3 = Вижу MP3, начинаю загрузку
done_mp3 = Вот твой готовый файл!
set_tags = Проставляем теги
downloaded = MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:
done_tag = Теги проставлены.\nЗагрузка началась, подождите около 2-5 минут
canceled = Отменено

main_episode = Основной эпизод
episode_aftershow = Эпизод послешоу

admin_panel_opened = Админ панель
admin_panel_open = Админ панель
admin_panel_close = Админ панель закрыта
admin_panel_main = [["Бот", "botPanel"]]
bot_commands = [["Выключить бота", "shutdown_bot"], ["Прислать лог-файлы", "send_logs"]]

ask_template = {
    .main = |
        <pre language="text">Number: 600
        Title: Название эпизода
        Comment: Описание эпизода
        Tags: Окно, жесть, спина
        Chapters: |
        00:00:07 - Вступление и что нового за неделю
        00:28:53 - Название темы 1
        01:40:56 - Название темы 2
        02:17:25 - Озвучили наших патронов и анонсировали послешоу</pre>
    .aftershow = |
        <pre language="text">Number: 600
        Title: Послешоу. Название эпизода
        Comment: Описание эпизода</pre>
}
