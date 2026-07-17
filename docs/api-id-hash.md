# TELEGRAM_API_ID и TELEGRAM_API_HASH

`TELEGRAM_API_ID` и `TELEGRAM_API_HASH` — это учётные данные **приложения Telegram** (не бота),
которые выдаёт Telegram на [https://my.telegram.org](https://my.telegram.org).

> **Когда это нужно.** Для обычной работы ShareTube (облачный Bot API) они **не требуются**.
> Они нужны **только** если вы включаете опциональный **Local Bot API server**
> (`LOCAL_BOT_API_ENABLED=true`) — локальный сервер Bot API поднимает соединение с Telegram от
> имени приложения и требует эти значения. Подробности — [docs/local-bot-api.md](local-bot-api.md).

---

## Как получить api_id и api_hash

1. Откройте [https://my.telegram.org](https://my.telegram.org) в браузере.
2. Войдите под **своим номером телефона** (тем, что привязан к аккаунту Telegram). Придёт код
   подтверждения **в сам Telegram** (не по SMS) — введите его.
3. Перейдите в **API development tools**.
4. Если приложение ещё не создано — заполните форму:
   - **App title** — например, `ShareTube Local API`.
   - **Short name** — например, `sharetube`.
   - **Platform** — `Server` (или `Other`).
   - URL и прочие поля можно оставить пустыми/минимальными.
5. После создания страница покажет:
   - **App api_id** — число (например, `2040123`).
   - **App api_hash** — строка из 32 hex-символов (например, `a1b2c3d4e5f6...`).

Эти два значения и есть `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`.

---

## Куда прописать

В файл `.env` (создаётся из `.env.example`):

```dotenv
# ----- optional local bot api -----
LOCAL_BOT_API_ENABLED=true
LOCAL_BOT_API_BASE=http://telegram-bot-api:8081
TELEGRAM_API_ID=2040123
TELEGRAM_API_HASH=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

Если Local Bot API не используется — оставьте поля пустыми, а `LOCAL_BOT_API_ENABLED=false`.

После изменения `.env`:

```bash
docker compose --profile localbotapi up -d telegram-bot-api
docker compose up -d worker bot
```

---

## Безопасность

- **Это секреты уровня аккаунта.** `api_id`/`api_hash` привязаны к вашему личному Telegram-аккаунту,
  а не к боту. Их компрометация опаснее, чем утечка токена бота: их **нельзя «отозвать» кнопкой** —
  Telegram не позволяет пересоздавать их произвольно, поэтому обращайтесь с ними максимально бережно.
- **Никогда не коммитьте** их в Git. Они хранятся только в `.env` (файл в `.gitignore`).
- Не передавайте их в чатах, скриншотах, тикетах. В логах ShareTube они не печатаются.
- Не публикуйте `api_hash` в клиентском коде фронтенда — он используется только серверным
  контейнером `telegram-bot-api` внутри Docker-сети и наружу не выставляется.
- Одна пара `api_id`/`api_hash` может обслуживать локальный сервер, к которому подключаются ваши боты
  (через их `BOT_TOKEN`). Заводить отдельную пару под каждый бот не нужно.

---

## Проверка

После запуска локального сервера убедитесь, что контейнер поднялся без ошибок авторизации:

```bash
docker compose logs --tail=50 telegram-bot-api
```

Если в логах видны сообщения об инициализации сервера без ошибок `API id/hash` — значения указаны
верно. Ошибки вида `Error: API id is invalid` означают опечатку в `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`.
