# Тексты бота. Формат — простые сообщения Fluent, их читает FtlTranslator
# из sagenza-tgbot-sdk: `ключ = значение`, продолжение значения — строки с
# отступом, подстановки — { $имя }.

error_occurred = Произошла ошибка! Пожалуйста, попробуйте снова
invalid_input = Ошибка при вводе!
invalid_recording_date = Не понял дату записи. Укажи её как ДД.ММ.ГГГГ, например 26.07.2026, и не позже сегодняшнего дня.
download_failed = ❌ MP3 не загружен. Проверь файл и попробуй ещё раз.
episode_number_failed = ❌ Не удалось узнать номер эпизода: FTP не ответил.
    <code>{ $error }</code>
    Загрузка отменена, начни заново через /start.

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
audio_vk = VK Donut
audio_patreon = Patreon
audio_sponsr = Sponsr
audio_forward = Переслать в чат
ftp_upload = Загрузить подкаст на FTP
wp_upload = Загрузить подкаст на сайт
boosty_upload = Опубликовать aftershow на Boosty
vk_upload = Опубликовать aftershow для донов VK
patreon_upload = Опубликовать aftershow на Patreon
sponsr_upload = Опубликовать aftershow на Sponsr
paywalled_publishing = ⏳ Публикация aftershow на { $platform }...
forwarded = Переслали в чат!
forward_failed = Ошибка при пересылке, попробуйте позже

## Админ-панель

admin_panel = Админ панель
admin_bot = Бот
bot_panel = Управление ботом
bot_restart = Перезапустить бота
bot_logs = Прислать лог-файлы
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

## Заметки ведущих

admin_notes = Заметки ведущих
notes_groups = Заметки ведущих по группам. Добавить: /note #тема текст
notes_entries = Заметки группы
notes_usage = Напиши заметку после команды: /note #тема текст. Группы: { $tags }
collector_saved = Сохранено в #{ $tag }
collector_used = ✅ Использовано
collector_delete = 🗑 Удалить
collector_marked_used = Отмечено как использованное
collector_deleted = Удалено
collector_missing = Запись уже удалена
collector_open_message = Открыть сообщение

## Topics and questions from listeners

admin_topics = 💡 Темы и вопросы
topics_panel =
    Темы и вопросы от слушателей: один список для ведущих.
    Обсудили пункты? Напиши «удали 1, 3» или отметь номера кнопками под списком.
topics_show = 📋 Показать список
topics_add_topic = ➕ Тема
topics_add_question = ➕ Вопрос
topics_authors = 🚷 Авторы
topics_refresh = 🔄 Обновить
topics_remove_marked = Удалить отмеченные ({ $count })
topics_undo = ↩️ Вернуть
topics_kind_topic = ТЕМА
topics_kind_question = ВОПРОС
topics_list_title = Список тем и вопросов:
topics_list_empty = Список тем и вопросов пуст: пока никто ничего не предложил.
topics_marked = Отмечено: { $numbers }
topics_marked_count = Отмечено пунктов: { $count }
topics_marked_none = Ничего не отмечено
topics_mark_first = Сначала отметь пункты кнопками с номерами
topics_list_stale = Этот список устарел. Вот свежий: отмечай в нём.
topics_denied = Эта кнопка только для ведущих
topics_view_missing = Не помню, какой список показывал последним. Вот свежий: номера бери из него.
topics_numbers_unknown = В последнем списке пунктов: { $total }, а таких номеров в нём нет: { $numbers }. Ничего не удалил. Свежий список: /topics
topics_remove_usage = Напиши номера пунктов из последнего списка: /done 1 3 4 или «удали 1, 3, 4». Список: /topics
topics_removed = Удалил из списка:
topics_removed_more = … и ещё { $count }
topics_removed_gone = Уже были удалены раньше: { $numbers }
topics_removed_nothing = Этих пунктов в списке уже нет, их удалили раньше: { $numbers }
topics_restored = Вернул в список:
topics_undo_expired = Вернуть уже нельзя: прошло больше 10 минут или пункты уже вернули
topics_authors_title =
    Авторы пунктов из списка и бан-лист. Нажми на автора, чтобы заблокировать его или разблокировать.
    От заблокированного бот ничего не принимает. Его пункты остаются в списке, пока их не удалишь.
topics_authors_empty = Блокировать некого: в списке нет пунктов от слушателей, бан-лист пуст.
topics_author = 🚷 { $name } (пунктов: { $count })
topics_author_banned = ✅ Разблокировать { $name }
topics_ban_done = Автор заблокирован
topics_unban_done = Автор разблокирован
topics_added_topic = Добавил тему в список для ведущих. Спасибо!
topics_added_question = Добавил вопрос в список для ведущих. Спасибо!
topics_admin_added =
    Добавил в список:
    { $line }
topics_reply_no_text = В этом сообщении нет текста, добавлять нечего.
topics_refused_too_short = Слишком коротко: нужно хотя бы { $min } символов.
topics_refused_too_long = Слишком длинно: не больше { $max } символов.
topics_refused_limit = Пока хватит: не больше { $limit } тем и вопросов за сутки. Попробуй позже!
topics_refused_banned = Предлагать темы и вопросы тебе сейчас нельзя.
topics_refused_duplicate = Это сообщение уже добавляли в список.
topics_post_button = 📌 Кнопка «Предложить» в чат
topics_form_button = 💡 Предложить тему или вопрос
topics_form_invite = Есть тема для выпуска или вопрос ведущим? Нажми кнопку: анкету увидишь только ты.
topics_form_posted = Кнопка отправлена в { $chat }
topics_form_post_failed = Не удалось отправить кнопку в чат. Бот состоит в нём и может писать?
topics_form_command = Предложить тему или вопрос ведущим
topics_form_command_topic = Предложить тему для выпуска
topics_form_command_question = Задать вопрос ведущим
topics_form_kind = Что добавить в список для ведущих?
topics_form_kind_topic = 💡 Тему
topics_form_kind_question = ❓ Вопрос
topics_form_ask_topic =
    Какую тему обсудить в выпуске?
    Напиши её ответом на это сообщение, от { $min } до { $max } символов.
topics_form_ask_question =
    Какой вопрос задать ведущим?
    Напиши его ответом на это сообщение, от { $min } до { $max } символов.
topics_form_ask_topic_admin =
    Какую тему добавить в список?
    Напиши её следующим сообщением, до { $max } символов.
topics_form_ask_question_admin =
    Какой вопрос добавить в список?
    Напиши его следующим сообщением, до { $max } символов.
topics_form_confirm =
    Добавить в список для ведущих?
    { $kind } - { $text }
topics_form_cancelled = Хорошо, в другой раз.
topics_form_expired = Анкета устарела. Начни заново: /topic или /question.
topics_form_open_private = Открыть анкету в личке
topics_form_go_private = Показать анкету здесь не получилось. Открой её в личке бота:

## Episode transcript (experimental)

transcript_done = Расшифровал выпуск { $episode }: { $audio } мин аудио за { $minutes } мин. Текст во вложении.
transcript_keywords = Ключевые слова для хештегов: { $hashtags }
transcript_no_keywords = Ключевых слов не нашёл: в выпуске нет слов, которые звучат заметно чаще других.
transcript_failed = Не удалось расшифровать выпуск { $episode }: { $reason }
transcript_reason_out_of_memory = не хватило памяти
transcript_reason_timeout = расшифровка шла слишком долго
transcript_reason_interrupted = сервис дважды прервался посреди работы, скорее всего, не хватило памяти
transcript_reason_missing_file = файл выпуска не найден
transcript_reason_expired = задание слишком долго ждало в очереди, сервис расшифровки не был запущен
transcript_reason_failed = ошибка сервиса расшифровки, подробности в его логе
transcript_empty = В выпуске { $episode } не удалось разобрать ни слова: расшифровка пустая.
transcript_discussed = Похоже, в выпуске обсудили пункты { $numbers }: в списке выше они отмечены. Удалить из списка?
transcript_remove = Удалить отмеченные
transcript_keep = Оставить
transcript_kept = Хорошо, ничего не удаляю. Вот список без отметок.
