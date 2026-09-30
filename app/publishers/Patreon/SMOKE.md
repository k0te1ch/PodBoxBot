# Patreon: доступ и смоук

Публичный API Patreon v2 посты не создаёт — только читает кампании, уровни,
участников и посты. Поэтому publisher работает как веб-редактор patreon.com:
сессионная кука `session_id`, CSRF-подпись со страницы, JSON:API-запросы
(черновик → медиа на S3 → публикация с правилами доступа). Последовательность
запросов не проверена на живом аккаунте: доступа нет. Первый прогон ниже
покажет, совпадает ли она с тем, что шлёт редактор.

## Что нужно от владельца

1. Аккаунт автора с кампанией и платными уровнями.
2. Кука `session_id` из браузера (DevTools → Application → Cookies →
   `https://www.patreon.com`) и User-Agent того же браузера:

   ```sh
   docker compose run --rm publisher_patreon python smoke.py import-cookie
   ```

3. `PATREON_TIER_IDS` в `.env` — JSON-список id уровней, например
   `["1234567"]`. Пусто — пост для всех платных патронов.

## Проверка

```sh
docker compose run --rm publisher_patreon python smoke.py check
```

Печатает id кампании и правила доступа. Если здесь 403 со страницей
Cloudflare — httpx отбивают, следующий шаг — браузер Camoufox с той же кукой.

Тестовая публикация (пост увидят патроны, удалите его):

```sh
docker compose run --rm -v "$PWD/test.mp3:/app/files/test.mp3" \
  publisher_patreon python smoke.py publish --mp3 /app/files/test.mp3 --yes
```

## Если шаг упал

Опубликуйте аудиопост руками с открытыми DevTools (Network → Preserve log),
сохраните HAR в `secrets/patreon/patreon.har` и выполните:

```sh
docker compose run --rm publisher_patreon python smoke.py har /app/data/patreon.har
```

Выжимка покажет методы, пути и имена полей без значений — по ней правится
`patreon_client.py`. Сам HAR содержит сессию: не коммитьте его и удалите
после разбора.

После успешного прогона включите кнопку в боте: `PATREON_ENABLED=true`.
