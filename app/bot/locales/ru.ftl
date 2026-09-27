# Тексты бота. Формат — простые сообщения Fluent, их читает FtlTranslator
# из sagenza-tgbot-sdk: `ключ = значение`, продолжение значения — строки с
# отступом, подстановки — { $имя }.

error_occurred = Произошла ошибка! Пожалуйста, попробуйте снова
invalid_input = Ошибка при вводе!
invalid_recording_date = Не понял дату записи. Укажи её как ДД.ММ.ГГГГ, например 26.07.2026, и не позже сегодняшнего дня.
download_failed = ❌ MP3 не загружен. Проверь файл и попробуй ещё раз.

## Загрузка эпизода (диалог DialogEngine)

ask_typeEpisode = Привет <b>{ $first_name }</b>, что мы добавляем?
ask_mp3 = Загружаем <u><b>{ $type_episode }</b></u>. Ожидаю MP3 файл
got_mp3 = Вижу MP3, начинаю загрузку
done_mp3 = Вот твой готовый файл!
set_tags = Проставляем теги
downloaded = MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:
done_tag =
    Теги проставлены.
    Загрузка началась, подождите около 2-5 минут
canceled = Отменено

main_episode = Основной эпизод
episode_aftershow = Эпизод послешоу

ask_template_main =
    <pre language="text">Number: { $number }
    Recording Date: 26.07.2026
    Title: Название эпизода
    Comment: Описание эпизода
    Tags: Окно, жесть, спина
    Chapters: |
    00:00:07 - Вступление и что нового за неделю
    00:28:53 - Название темы 1
    01:40:56 - Название темы 2
    02:17:25 - Озвучили наших патронов и анонсировали послешоу</pre>
ask_template_aftershow =
    <pre language="text">Number: { $number }
    Recording Date: 26.07.2026
    Title: Послешоу. Название эпизода
    Comment: Описание эпизода</pre>

# Служебные тексты DialogEngine: ключ `de.x.y` ищется как `de-x-y`.
# Подстановки в них — в фигурных скобках без $, их заполняет сам движок.
de-button-back = ⬅️ Назад
de-button-cancel = Отмена
de-button-keep = Оставить
de-button-keep_value = Оставить: {value}
de-error-media-mime = Нужен MP3 (допустимые типы: {allowed})
de-error-media-extension = Нужен файл с расширением {allowed}
de-error-media-size = Файл больше {max_mb} МБ
de-error-file-expected = Жду MP3 файл
de-error-media-unexpected = Здесь нужен текст, а не файл
de-error-button_required = Выбери вариант кнопкой
de-alert-no_session = Диалог уже закончился, начни заново: /start
de-alert-stale_button = Кнопка устарела
de-alert-expired = Диалог устарел, начни заново: /start

## Меню аудио

audio_ftp = FTP
audio_site = Сайт
audio_boosty = Boosty
audio_forward = Переслать в чат
ftp_upload = Загрузить подкаст на FTP
wp_upload = Загрузить подкаст на сайт
boosty_upload = Опубликовать aftershow на Boosty
forwarded = Переслали в чат!
forward_failed = Ошибка при пересылке, попробуйте позже

## Админ-панель

admin_panel = Админ панель
admin_bot = Бот
bot_panel = Управление ботом
bot_shutdown = Выключить бота
bot_restart = Перезапустить бота
bot_logs = Прислать лог-файлы
bot_shutting_down = Бот выключается
bot_restarting = Бот перезапускается
logs_failed = Ошибка: не удалось собрать логи

## Сервисные сообщения

admin_service = Сервисное сообщение
service_ask_text = Напиши текст сообщения — после подтверждения он уйдёт в { $chat }
service_confirm = Отправить это сообщение в { $chat }?
service_sent = Отправили в { $chat }
service_failed = Не удалось отправить сообщение, попробуйте позже
de-button-confirm = ✅ Отправить

## Новый эпизод в RSS

rss_new_episode = Вышел эпизод { $number }: { $title }. Выложить?
rss_no_mp3 = В ленте нет mp3 нашего выпуска — для FTP, сайта и Boosty загрузи файл через /start
rss_to_chat = В чат
rss_prepare = На площадки (FTP, сайт, Boosty)
rss_skip = Не надо
rss_chat_post = Вышел новый эпизод: { $title }
    { $link }
rss_done_chat = анонс отправлен в чат
rss_done_prepare = mp3 скачан, выбери площадку в меню под файлом
rss_done_skip = не выкладываем
rss_cannot_prepare = нет mp3 или номера эпизода, загрузи файл через /start
rss_choice = { $user }: { $result }
rss_expired = Уведомление устарело
rss_feed_down = RSS не читается уже { $count } раз подряд: { $url }

## Заметки ведущих и вопросы слушателей

admin_notes = Заметки ведущих
admin_questions = Вопросы слушателей
notes_groups = Заметки ведущих по группам. Добавить: /note #тема текст
questions_groups = Вопросы и темы слушателей по хештегам
notes_entries = Заметки группы
questions_entries = Вопросы группы
notes_usage = Напиши заметку после команды: /note #тема текст. Группы: { $tags }
questions_usage = Напиши вопрос после команды: /ask текст. Можно указать хештег: { $tags }
collector_saved = Сохранено в #{ $tag }
collector_used = ✅ Использовано
collector_delete = 🗑 Удалить
collector_marked_used = Отмечено как использованное
collector_deleted = Удалено
collector_missing = Запись уже удалена
collector_open_message = Открыть сообщение
