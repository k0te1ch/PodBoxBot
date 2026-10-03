# Тексты бота. Формат — простые сообщения Fluent, их читает FtlTranslator
# из sagenza-tgbot-sdk: `ключ = значение`, продолжение значения — строки с
# отступом, подстановки — { $имя }.

error_occurred = Что-то пошло не так, попробуй ещё раз
invalid_input = Не разобрал описание. Проверь, что строки Number, Title и Comment на месте, как в шаблоне
invalid_recording_date = Не понял дату записи. Выбери её кнопкой или напиши как ДД.ММ.ГГГГ, например 26.07.2026, не позже сегодняшнего дня
invalid_publish_at = Не понял дату публикации. Выбери её кнопками или напиши дату и время, например 05.10.2026 20:00, не раньше текущего момента
download_failed = не скачался. Проверь файл и пришли его ещё раз
episode_number_failed = FTP не ответил, загрузка отменена. Начни заново: /new
    <code>{ $error }</code>

## Загрузка эпизода (диалог DialogEngine)

ask_typeEpisode = Какой выпуск оформляем?
ask_typeEpisode_for_file = Вижу mp3. Это основной выпуск или послешоу?
file_not_mp3 = Это не mp3. Чтобы оформить выпуск, пришли mp3 или нажми «Новый выпуск» в /start
ask_mp3 = Оформляем: <b>{ $type_episode }</b>. Пришли mp3
got_mp3 = Вижу mp3, скачиваю
done_mp3 = Выпуск готов. Куда выкладываем?
canceled = Отменил

## Даты выпуска (utils/date_picker.py)

summary_file = ✅ Файл получен ({ $size }), это будет выпуск { $number }
summary_recording = Выпуск { $number } · запись { $recording }
summary_dates = Выпуск { $number } · запись { $recording } · публикация { $publish }
ask_recording_date = Когда записывали выпуск?
ask_publish_at = Когда публикуем? «Как обычно»: дату не задаём, сайт сохранит черновик, остальные площадки сработают сразу
date_today = Сегодня, { $date }
date_yesterday = Вчера, { $date }
date_other = 📅 Другая дата
date_back = « К быстрому выбору
date_publish_default = Как обычно
date_publish_default_short = как обычно
date_publish_today = Сегодня
date_publish_tomorrow = Завтра
date_day_month = { $day } { $month }
months = Январь Февраль Март Апрель Май Июнь Июль Август Сентябрь Октябрь Ноябрь Декабрь
months_genitive = января февраля марта апреля мая июня июля августа сентября октября ноября декабря
weekdays = Пн Вт Ср Чт Пт Сб Вс

## Статус-сообщение долгой операции (utils/status_message.py)

status_download = Скачиваю файл
status_download_done = Файл получен
status_number = Узнаю номер выпуска
status_number_done = Номер выпуска известен
status_description = Дальше: описание выпуска
status_tags = Ставлю теги и обложку
status_tags_done = Теги и обложка на месте
status_send = Отправляю готовый файл
status_send_done = Файл отправлен
status_episode_title = 🎙 Выпуск { $number }: { $title }
status_tags_failed = не получилось. Начни заново: /new
    <code>{ $error }</code>
status_send_failed = Telegram не принял файл. Начни заново: /new
    <code>{ $error }</code>
status_kilobytes = КБ
status_megabytes = МБ
status_seconds = { $seconds } с
status_minutes = { $minutes } мин { $seconds } с
status_of = { $done } из { $total }
status_left = ещё ~{ $time }
status_slow = уже { $time }, дольше обычного, но я жду

main_episode = Основной выпуск
episode_aftershow = Послешоу

ask_template_main =
    Теперь пришли описание. Скопируй шаблон и поменяй только значения:
    <pre language="text">Number: { $number }
    Title: Название эпизода
    Comment: Описание эпизода
    Tags: Окно, жесть, спина
    Chapters: |
    00:00:07 - Вступление и что нового за неделю
    00:28:53 - Название темы 1
    01:40:56 - Название темы 2
    02:17:25 - Озвучили наших патронов и анонсировали послешоу</pre>
ask_template_aftershow =
    Теперь пришли описание. Скопируй шаблон и поменяй только значения:
    <pre language="text">Number: { $number }
    Title: Послешоу. Название эпизода
    Comment: Описание эпизода</pre>

# Служебные тексты DialogEngine: ключ `de.x.y` ищется как `de-x-y`.
# Подстановки в них — в фигурных скобках без $, их заполняет сам движок.
de-button-back = ⬅️ Назад
de-button-cancel = Отмена
de-button-keep = Оставить
de-button-keep_value = Оставить: {value}
de-error-media-mime = Нужен mp3, а это другой файл
de-error-media-extension = Нужен файл с расширением {allowed}
de-error-media-size = Файл больше {max_mb} МБ
de-error-file-expected = Жду mp3 файлом
de-error-media-unexpected = Здесь нужен текст, а не файл
de-error-button_required = Выбери вариант кнопкой
de-alert-no_session = Этот диалог уже закончился. Новый выпуск: /new
de-alert-stale_button = Кнопка устарела
de-alert-expired = Диалог устарел. Новый выпуск: /new

## Меню аудио

audio_ftp = FTP
audio_site = Сайт
audio_boosty = Boosty
audio_vk = VK Donut
audio_patreon = Patreon
audio_sponsr = Sponsr
audio_forward = В чат
ftp_upload = Загрузить на FTP
wp_upload = Сохранить черновик на сайте
boosty_upload = Опубликовать послешоу на Boosty
vk_upload = Опубликовать послешоу для донов VK
patreon_upload = Опубликовать послешоу на Patreon
sponsr_upload = Опубликовать послешоу на Sponsr
forwarded = Переслал в чат
forward_failed = Не получилось переслать, причина в сообщении ниже

## Админ-панель

home_admin = Привет! Что делаем?
home_user = Привет! Это бот подкаста. Здесь можно предложить тему для выпуска или задать вопрос ведущим
home_new_episode = 🎙 Новый выпуск
home_admin_panel = ⚙️ Админка
home_help = ❓ Как это работает
help_text =
    Напиши /topic, чтобы предложить тему для выпуска, или /question, чтобы задать вопрос ведущим.
    Можно и сразу с текстом: /question почему небо голубое?
    Ведущие увидят всё в общем списке и разберут в одном из выпусков

admin_panel = Админка
bot_restart = Перезапустить
bot_logs = Логи
bot_restarting = Перезапускаюсь, вернусь через минуту
logs_failed = Не получилось собрать логи

## Сервисные сообщения

admin_service = Сообщение в чат
service_ask_text = Напиши текст сообщения. После подтверждения он уйдёт в { $chat }
service_confirm = Отправить это сообщение в { $chat }?
service_sent = Отправили в { $chat }
service_failed = Не получилось отправить, попробуй позже
de-button-confirm = ✅ Отправить

## Новый эпизод в RSS

rss_new_episode = Вышел эпизод { $number }: { $title }. Выложить?
rss_no_mp3 = В ленте нет mp3 этого выпуска. Для FTP, сайта и Boosty пришли файл сам
rss_to_chat = В чат
rss_prepare = На площадки
rss_skip = Не надо
rss_chat_post = Вышел новый выпуск: <a href="{ $link }">{ $title }</a>
rss_download_failed = mp3 не скачался, попробуй позже
rss_done_chat = анонс отправлен в { $chat }
rss_done_prepare = mp3 скачан, выбери площадку в меню под файлом
rss_done_skip = не выкладываем
rss_cannot_prepare = в ленте нет mp3 или номера выпуска, пришли файл сам
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
topics_panel = Темы и вопросы от слушателей
topics_show = 📋 Список
topics_add_topic = ➕ Тема
topics_add_question = ➕ Вопрос
topics_authors = 🚷 Авторы
topics_refresh = 🔄 Обновить
topics_remove_marked = Удалить отмеченные ({ $count })
topics_undo = ↩️ Вернуть
topics_kind_topic = ТЕМА
topics_kind_question = ВОПРОС
topics_list_heading = Темы и вопросы
topics_column_number = №
topics_column_kind = Тип
topics_column_text = Текст
topics_column_author = От кого
topics_column_when = Когда
topics_list_title = Список тем и вопросов:
topics_list_empty = Список пуст: пока никто ничего не предложил
topics_marked = Отмечено: { $numbers }
topics_marked_count = Отмечено пунктов: { $count }
topics_marked_none = Ничего не отмечено
topics_mark_first = Сначала отметь пункты кнопками с номерами
topics_list_stale = Этот список устарел. Вот свежий: отмечай в нём
topics_denied = Эта кнопка только для ведущих
topics_view_missing = Не помню, какой список показывал последним. Вот свежий: номера бери из него
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
    От заблокированного бот ничего не принимает. Его пункты остаются в списке, пока их не удалишь
topics_authors_empty = Блокировать некого: в списке нет пунктов от слушателей, бан-лист пуст
topics_author = 🚷 { $name } (пунктов: { $count })
topics_author_banned = ✅ Разблокировать { $name }
topics_ban_done = Автор заблокирован
topics_unban_done = Автор разблокирован
topics_added_topic = Добавил тему в список для ведущих, спасибо
topics_added_question = Добавил вопрос в список для ведущих, спасибо
topics_admin_added =
    Добавил в список:
    { $line }
topics_reply_no_text = В этом сообщении нет текста, добавлять нечего
topics_refused_too_short = Слишком коротко: нужно хотя бы { $min } символов
topics_refused_too_long = Слишком длинно: не больше { $max } символов
topics_refused_limit = Пока хватит: не больше { $limit } тем и вопросов за сутки. Приходи завтра
topics_refused_banned = Предлагать темы и вопросы тебе сейчас нельзя
topics_refused_duplicate = Это сообщение уже добавляли в список
topics_post_button = 📌 Кнопка «Предложить» в чат
topics_form_button = 💡 Предложить тему или вопрос
topics_form_invite = Есть тема для выпуска или вопрос ведущим? Нажми кнопку: анкету увидишь только ты
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
    Напиши её ответом на это сообщение, от { $min } до { $max } символов
topics_form_ask_question =
    Какой вопрос задать ведущим?
    Напиши его ответом на это сообщение, от { $min } до { $max } символов
topics_form_ask_topic_admin =
    Какую тему добавить в список?
    Напиши её следующим сообщением, до { $max } символов
topics_form_ask_question_admin =
    Какой вопрос добавить в список?
    Напиши его следующим сообщением, до { $max } символов
topics_form_confirm =
    Добавить в список для ведущих?
    { $kind } - { $text }
topics_form_cancelled = Хорошо, в другой раз
topics_form_expired = Анкета устарела. Начни заново: /topic или /question
topics_form_open_private = Открыть анкету в личке
topics_form_go_private = Показать анкету здесь не получилось. Открой её в личке бота:

## /status

status_title = PodBoxBot: состояние
status_version = Версия
status_uptime = Работает
status_updates = Обработано сообщений
status_errors = Ошибок
status_rss = Слежение за лентой
status_topics = Тем и вопросов в списке
status_on = включено
status_off = выключено
status_publications = Последние публикации
status_publications_none = После запуска бота публикаций не было
status_column_what = Что
status_column_value = Значение
status_column_episode = Выпуск
status_column_platform = Площадка
status_column_state = Состояние
status_column_when = Когда

## Устаревшие кнопки

episode_file_gone = Этот файл уже заменён новым выпуском. Чтобы выложить его, оформи выпуск заново: /new
publish_sent = Отправил, статус ниже
publish_send_failed = Не получилось отправить запрос, причина в статусе ниже
