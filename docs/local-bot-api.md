# Local Bot API server

Telegram предлагает два способа обращаться к Bot API:

| | Облачный Bot API (`api.telegram.org`) | Local Bot API server (свой контейнер) |
|---|---|---|
| Лимит отправки файла ботом | ~50 МБ | ~2 ГБ |
| Отправка файла | только загрузкой (upload) | можно **по локальному пути** без повторной загрузки |
| Нужны api_id/api_hash | нет | **да** |
| Требует ресурсов сервера | нет | да (доп. контейнер, ~100+ МБ RAM) |

ShareTube по умолчанию использует **облачный** Bot API и безопасные лимиты доставки из конфигурации:

```dotenv
CLOUD_BOT_SAFE_LIMIT_MB=45     # облачный Bot API: отправляем в Telegram файлы до 45 МБ
LOCAL_BOT_SAFE_LIMIT_MB=1900   # local Bot API: до ~1900 МБ (запас до предела ~2 ГБ)
```

Файлы больше лимита не «ломаются»: ShareTube отдаёт их **временной подписанной ссылкой**
(`DOWNLOAD_LINK_TTL_HOURS=24`) и, где уместно, предлагает более низкое качество или только звук.
Решение о способе доставки принимается по **фактическому** размеру файла
(`apps/backend/app/services/delivery.py`).

> На слабом сервере (см. `SERVER_AUDIT.md`, 2 ГиБ RAM) Local Bot API держать постоянно
> нецелесообразно — облачного лимита 45 МБ + подписанных ссылок обычно достаточно. Включайте
> локальный сервер, когда действительно нужна регулярная отправка крупных файлов (до ~2 ГБ)
> прямо в Telegram.

---

## Когда включать

Включайте Local Bot API, если нужно **отправлять в Telegram файлы больше ~50 МБ** (до ~2 ГБ) без
временных ссылок — например, длинные видео в 1080p.

---

## Как включить

1. Получите `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` — см. [docs/api-id-hash.md](api-id-hash.md).
2. В `.env`:

   ```dotenv
   LOCAL_BOT_API_ENABLED=true
   LOCAL_BOT_API_BASE=http://telegram-bot-api:8081
   TELEGRAM_API_ID=<ваш_api_id>
   TELEGRAM_API_HASH=<ваш_api_hash>
   LOCAL_BOT_SAFE_LIMIT_MB=1900
   ```

3. **ВАЖНО (миграция бота на локальный сервер):** перед переключением бота на локальный сервер
   нужно **разлогинить токен в облачном Bot API** (иначе локальный сервер не сможет принять сессию):

   ```bash
   curl "https://api.telegram.org/bot<BOT_TOKEN>/logOut"
   ```

   Дождитесь ответа `{"ok":true,"result":true}`. Подставьте реальный токен вместо `<BOT_TOKEN>`.

4. Запустите локальный сервер и перезапустите зависимые сервисы:

   ```bash
   docker compose --profile localbotapi up -d telegram-bot-api
   docker compose up -d worker bot
   ```

5. Проверьте логи:

   ```bash
   docker compose logs --tail=50 telegram-bot-api
   docker compose logs --tail=50 bot
   ```

---

## Общий том (файлы без повторной загрузки)

Ключевое преимущество локального сервера — отправка файла **по локальному пути**. Для этого
том хранилища `st_storage` смонтирован **в оба** контейнера по одному и тому же пути
`/data/storage`:

```yaml
# docker-compose.yml (фрагмент)
worker:
  volumes:
    - st_storage:/data/storage
    - st_tmp:/data/tmp

telegram-bot-api:
  profiles: ["localbotapi"]
  command: ["--local", "--dir=/data/storage"]
  volumes:
    - st_storage:/data/storage          # тот же том, что у worker
    - st_botapi:/var/lib/telegram-bot-api
```

Так worker сохраняет файл в `/data/storage/...`, а `telegram-bot-api` читает **тот же самый файл**
по тому же пути — Telegram не перезагружает его с диска на сервер повторно. Это и даёт отправку
крупных файлов быстро и без двойного трафика.

### Абсолютные локальные пути

В режиме `--local` Telegram Bot API принимает поле файла как **абсолютный путь на своей файловой
системе** (например, `/data/storage/2026/07/<token>.mp4`), а не как `multipart`-загрузку. Поэтому
критично, чтобы путь, который видит `worker`, совпадал с путём внутри контейнера `telegram-bot-api`
— это обеспечивается одинаковой точкой монтирования `/data/storage`. Не меняйте `--dir` и точки
монтирования по отдельности.

---

## Возврат на облачный Bot API

Симметрично: перед возвратом на облако нужно **разлогинить токен на локальном сервере**.

1. Разлогиньте бота на локальном сервере (внутри Docker-сети локальный сервер слушает `:8081`):

   ```bash
   docker compose exec app sh -c 'curl "http://telegram-bot-api:8081/bot<BOT_TOKEN>/logOut"'
   ```

   Дождитесь `{"ok":true,"result":true}`.

2. В `.env`:

   ```dotenv
   LOCAL_BOT_API_ENABLED=false
   ```

3. Остановите локальный сервер и перезапустите бота/worker:

   ```bash
   docker compose stop telegram-bot-api
   docker compose up -d worker bot
   ```

После `logOut` тот же токен снова начнёт работать через `api.telegram.org`.

---

## Правило миграции (кратко)

| Переход | Что сделать ДО переключения |
|---|---|
| Облако → Local | `curl https://api.telegram.org/bot<TOKEN>/logOut` |
| Local → Облако | `curl http://telegram-bot-api:8081/bot<TOKEN>/logOut` (изнутри Docker-сети) |

Если пропустить `logOut`, целевой сервер вернёт ошибку вида «bot is already in use / logged in on
another server», и бот не сможет отправлять сообщения, пока сессия не будет корректно закрыта.

---

## Диагностика

```bash
# состояние контейнера и его логи
docker compose ps telegram-bot-api
docker compose logs -f telegram-bot-api

# проверить, что worker видит тот же файл, что и bot-api
docker compose exec worker ls -la /data/storage
docker compose exec telegram-bot-api ls -la /data/storage
```

| Симптом | Решение |
|---|---|
| `API id is invalid` | Опечатка в `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`. |
| `logged in on another server` | Не сделан `logOut` на прежнем сервере (см. таблицу выше). |
| Крупные файлы всё равно идут ссылкой | `LOCAL_BOT_API_ENABLED` не `true`, либо файл > `LOCAL_BOT_SAFE_LIMIT_MB`. |
| `file must be non-empty` / путь не найден | Рассинхрон точек монтирования `/data/storage`. |
