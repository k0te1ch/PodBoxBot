# Sponsr: доступ и калибровка

API у Sponsr нет. Publisher работает как веб-редактор по сессионной куке
`SESS` (так же авторизуется открытый клиент sponsrdump). Запросы сверены с
записью ручной публикации поста с mp3 для подписчиков:

1. страница `/<slug>/manage/post/new/`: id проекта и уровень подписки,
   выбранный по умолчанию;
2. `resumable-file`: mp3 кусками по 5 МБ, после каждого
   `upload-file-info/update-chunk-file`, затем `complete-file`, ожидание
   `file-state` = `completed` и `update-file-state`;
3. `post-save/new`: форма редактора, замок — `level_id` (уровень подписки),
   `media_file` — загруженный файл.

Проверка на живом аккаунте (смоук ниже) ещё не проходила.

## Что нужно от владельца

1. Кабинет автора с проектом и платной подпиской; `SPONSR_PROJECT` — slug
   проекта (`sponsr.ru/<slug>`).
2. Кука `SESS` и User-Agent браузера:

   ```sh
   docker compose run --rm publisher_sponsr python smoke.py import-cookie
   docker compose run --rm publisher_sponsr python smoke.py check
   ```

   `check` печатает id проекта и уровень подписки для замка. Нужен другой
   уровень: `SPONSR_LEVEL_ID` в `.env` (value из списка «Кому доступен» в
   редакторе).

## Проверка

Тестовая публикация (пост увидят подписчики, удалите его):

```sh
docker compose run --rm -v "$PWD/test.mp3:/app/files/test.mp3" \
  publisher_sponsr python smoke.py publish --mp3 /app/files/test.mp3 --yes
```

Если шаг упал, запишите HAR ручной публикации (DevTools → Network →
Preserve log, «Save all as HAR» в `secrets/sponsr/sponsr.har`) и выполните
`python smoke.py har /app/data/sponsr.har`: выжимка покажет методы, пути и
имена полей без значений. HAR содержит сессию: не коммитьте его и удалите
после разбора.

Кнопка в боте включается `SPONSR_ENABLED=true` после успешного прогона.
