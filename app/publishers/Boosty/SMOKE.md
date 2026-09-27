# Смоук Boosty на живом блоге

Publisher покрыт тестами на моках, но живой internal API Boosty ими не
проверяется. Этот прогон — единственный способ убедиться, что Boosty
принимает наши запросы. Нужен аккаунт автора блога.

## 1. Токены

Программного логина у Boosty нет, токены берутся из браузера.

1. Войдите на boosty.to под аккаунтом автора.
2. DevTools → Application → Cookies → `https://boosty.to`. Понадобятся значения
   кук `auth` (URL-encoded JSON с `accessToken`/`refreshToken`/`expiresAt`) и
   `_clientId` (это `device_id` для обновления токена).
3. Запишите их в `secrets/boosty/boosty_auth.json`:

   ```sh
   docker compose run --rm publisher_boosty python smoke.py import-cookie
   ```

   Значения вводятся скрытым вводом и в историю shell не попадают. Файл потом
   перезаписывает сам сервис при каждом обновлении токена — ему нужны права
   на запись.

Дальше токен обновляется автоматически: заранее, если до истечения меньше
десяти минут, по 401 и раз в час фоновой задачей. Если Boosty отклонил
refresh_token (сменили пароль, вышли из всех сессий), бот покажет ошибку
«Boosty: refresh_token отклонён… Обновите secrets/boosty/boosty_auth.json» —
повторите шаги выше.

## 2. Проверка без публикации

```sh
docker compose run --rm publisher_boosty python smoke.py check
```

Команда обновляет токен, читает блог и печатает уровни подписки. Из вывода
заполните в `.env`:

- `BOOSTY_BLOG` — slug блога (`boosty.to/<slug>`);
- `BOOSTY_OWNER_ID` — ownerId блога;
- `BOOSTY_SUBSCRIPTION_LEVEL_ID` — id платного уровня;
- `BOOSTY_PRICE` — цена поста, ₽;
- `BOOSTY_ENABLED=true` в `.env` бота, чтобы кнопка появилась в меню послешоу.

## 3. Тестовая публикация

Пост увидят платные подписчики — публикуйте в тихое время и сразу удаляйте.
Черновик в редакторе Boosty один на блог, публикация его перезапишет.

```sh
docker compose run --rm -v "$PWD/test.mp3:/app/files/test.mp3" \
  publisher_boosty python smoke.py publish --mp3 /app/files/test.mp3 --yes
```

Успех — строка `пост: https://boosty.to/<blog>/posts/<id> (найден через API: True)`.
Если шаг упал, в ошибке будет его имя (`upload audio init`, `save draft`,
`publish`) и ответ Boosty — чинить нужно `boosty_client.py`.

## 4. Прогон из бота

Поднимите `publisher_boosty`, оформите короткое послешоу и нажмите
«Boosty → Опубликовать aftershow на Boosty». Проверьте на блоге: пост доступен
только платному уровню, mp3 играется, обложка стоит в тизере, бот показал
успех со ссылкой.
