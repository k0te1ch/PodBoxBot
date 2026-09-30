# Sponsr: доступ и калибровка

API у Sponsr нет. Publisher работает как веб-редактор по сессионной куке
`SESS` (так же авторизуется открытый клиент sponsrdump). Сессия и проверка
входа готовы, а запросы публикации нигде не описаны и без кабинета автора их
не снять — угадывать их мы не стали. Пока они не дописаны, событие Sponsr
заканчивается понятной ошибкой «запросы публикации ещё не сняты с редактора».

## Что нужно от владельца

1. Кабинет автора с проектом и платной подпиской; `SPONSR_PROJECT` — slug
   проекта (`sponsr.ru/<slug>`).
2. Кука `SESS` и User-Agent браузера:

   ```sh
   docker compose run --rm publisher_sponsr python smoke.py import-cookie
   docker compose run --rm publisher_sponsr python smoke.py check
   ```

3. HAR ручной публикации: DevTools → Network → Preserve log, опубликовать
   тестовый пост с аудио только для подписчиков, «Save all as HAR» в
   `secrets/sponsr/sponsr.har`, затем:

   ```sh
   docker compose run --rm publisher_sponsr python smoke.py har /app/data/sponsr.har
   ```

   Выжимка (методы, пути, имена полей, CSRF-заголовки — без значений)
   достаточна, чтобы дописать `SponsrClient.publish`. HAR содержит сессию:
   не коммитьте его и удалите после разбора.

Кнопка в боте включается `SPONSR_ENABLED=true` только после этого.
