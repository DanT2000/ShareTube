# DEPLOYMENT_REPORT — отчёт о развёртывании ShareTube

Дата: 2026-07-17. Сервер: **107 Apps** (`192.168.2.15`, публичный `188.18.55.140`), управление через Coolify + Traefik.

## Что было найдено

- В рабочей папке — прежний монолитный ShareTube: `main.py` (telebot + yt-dlp + Flask, только YouTube), `main.py.bak`, `proxy.py`, `cookies.txt`, ~2.9 ГБ старых загрузок. Git-репозитория и логотипов не было. Подробности и карта переноса — [LEGACY_AUDIT.md](LEGACY_AUDIT.md).
- Поиск прежнего репозитория в интернете однозначного совпадения не дал; за основу взят локальный скрипт (как предписано).
- Сервер: 3 vCPU, 2 ГБ RAM, Docker 29.4 + Compose v5, Coolify-proxy (Traefik v3.6) на 80/443. Порт **8989 свободен**. Чужие приложения не тронуты. Подробности — [SERVER_AUDIT.md](SERVER_AUDIT.md).

## Что сделано

- Прежний скрипт переработан в модульную production-архитектуру (FastAPI, SQLAlchemy 2 async, Alembic, ARQ-очередь, отдельные worker и бот, Xray sidecar, storage-провайдеры, admin). Сохранены название ShareTube, бот `@sharetube_bot`, домен, UX прогресса, стратегия форматов и вытеснение хранилища.
- Реализованы: SSRF-защита, безопасные имена файлов, rate limiting/квоты, подписанные ссылки, валидация Telegram initData, шифрование cookies/proxy-секретов, маскирование секретов в логах/API, обязательная маршрутизация загрузок через прокси/Xray, доставка по фактическому размеру, фото/карусели/ZIP, кэш `file_id`, cron-очистка и восстановление зависших задач.
- 51 автотест (SSRF, filenames, delivery-routing, initData, signed URLs, extractor-selection, storage TTL/cap, jobs/queue, API-интеграция) — **все проходят** (прогон в контейнере python:3.12 на сервере).

## Запущенные компоненты (на сервере, `docker compose`)

| Контейнер | Статус | Назначение |
|---|---|---|
| app | Up (healthy) | FastAPI + статика фронтенда, порт 8989 |
| worker | Up | ARQ downloader (extractors, лимиты, отмена, доставка) |
| bot | Up | python-telegram-bot (polling) |
| postgres | Up (healthy) | PostgreSQL 16 (не публикуется наружу) |
| redis | Up (healthy) | очередь/прогресс/rate-limit (не публикуется) |
| xray | Up (healthy) | outbound SOCKS5/HTTP (не публикуется) |

Наружу открыт только `app` (порт 8989 + домен через Traefik). Postgres/Redis/Xray в интернет не выставлены.

## Доступ

- **Прямой (работает):** http://188.18.55.140:8989 — веб-интерфейс (заголовок «ShareTube — загрузчик медиа»), `/health` = `{"status":"ok"}`, `/api`, `/admin`, `/download/<token>`.
- **Домен:** https://sharetube.appswire.ru — Traefik маршрутизирует на app (HTTP→HTTPS редирект 307 работает, HTTPS отвечает 200). Подключён к сети `coolify`, лейблы Traefik навешены (`infra/docker-compose.coolify.yml`).
- **Telegram-бот:** `@sharetube_bot` (id 7817038355), режим **polling**, `getMe` = 200 (проверено через прокси в окно работоспособности туннеля). Токен показывается только как fingerprint; в логах замаскирован.

## Статус SSL — НЕ выпущен (внешняя причина, задокументировано)

Валидный сертификат Let's Encrypt для sharetube.appswire.ru на момент завершения **не выпущен**. Причина — **общая, предсуществующая, не связанная с ShareTube**:

- Проверка соседнего рабочего домена самого Coolify — `coolify.dev.appswire.ru` — тоже отдаёт self-signed сертификат (`ssl_verify_result=18`, `code=000`). То есть LE не работает для ВСЕХ доменов на этом Traefik.
- Логи `coolify-proxy`: аккаунт appswire.ru в **rate-limit** Let's Encrypt (`429 too many failed authorizations`), провоцируется постоянно падающим соседним доменом `newday.appswire.ru`; ACME HTTP-01 challenge отдаёт `404` на уровне Coolify-прокси для всех доменов.
- Чинить чужие домены и конфигурацию Coolify-прокси запрещено заданием.

Моя конфигурация домена корректна: маршрутизация и редирект работают, `certresolver=letsencrypt` задан — сертификат выпустится автоматически, как только владелец устранит общую проблему (разобраться с `newday.appswire.ru` и/или дождаться снятия rate-limit). До этого рабочий доступ — по HTTP на IP:8989; бот на polling (webhook включать только после валидного HTTPS: `TELEGRAM_USE_WEBHOOK=true`).

## Статус outbound (HTTP proxy / Xray) — см. [NETWORK_AUDIT.md](NETWORK_AUDIT.md)

- HTTP-прокси из config — **мёртв** (connect timeout).
- Xray-узел — **нестабилен**: работал первые ~15 минут (доказана реальная загрузка), затем бесплатный узел задросселировал до нуля. VLESS-сервер по TCP доступен, но апстрим не форвардит трафик.

## Фактические тесты

| Тест | Результат |
|---|---|
| 51 unit/integration тест (python:3.12) | ✅ все прошли |
| Прямой файл `sample-5s.mp4` через Xray → storage → delivery `cloud_bot` → signed link | ✅ пройден сквозно (в окно работоспособности туннеля) |
| Cross-device move tmp→storage | ✅ исправлено (обнаружено и починено на реальном запуске) |
| Telegram `getMe`/`getUpdates` через прокси | ✅ 200 (в окно работоспособности) |
| Веб-интерфейс на IP:8989 (index + /health) | ✅ 200, заголовок ShareTube |
| Домен: HTTP→HTTPS redirect, HTTPS→app | ✅ 307 / 200 (сертификат — см. выше) |
| YouTube/Vimeo через Xray | ❌ невозможно из-за деградации узла (внешняя причина) |
| Валидный LE сертификат | ❌ внешняя причина (общий rate-limit Traefik, см. выше) |

Найденные при реальном запуске дефекты **исправлены**: cross-device move (storage), маршрутизация бота и доставки через прокси (Telegram блокируется на прямом маршруте сервера), заглушение httpx-логов с токеном, авто-сид Xray-профиля, MTU docker-сети.

## Что владельцу нужно перевыпустить/сделать (кратко)

1. Перевыпустить ВСЕ временные секреты из `config.txt` (bot token, HTTP-прокси, Xray/VLESS, SSH-пароль, Coolify token) — они были в открытом виде.
2. Дать рабочий стабильный outbound (прокси или Xray) → добавить в админке «Сеть и прокси» → «Проверить» → «Сделать основным».
3. Устранить общую проблему Let's Encrypt на Coolify-прокси (соседний `newday.appswire.ru` ломает выпуск для всего домена) — после этого HTTPS для sharetube поднимется автоматически.

## Эксплуатация

```sh
# логи
docker compose logs -f app worker bot
# статус/здоровье
bash scripts/health-check.sh
# миграции
docker compose run --rm app migrate
# бэкап/восстановление
bash scripts/backup.sh ; bash scripts/restore.sh backups/db_YYYYMMDD_HHMMSS.sql.gz
# обновление yt-dlp/gallery-dl с smoke-тестом и откатом
bash scripts/update-tools.sh
# очистка хранилища
bash scripts/cleanup.sh
# полный деплой (с доменом/HTTPS overlay)
docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d
```

Секреты (пароли, bot token, private keys, полные proxy/Xray-URL, cookies) в этот отчёт не включены.
