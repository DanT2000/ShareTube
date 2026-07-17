# ShareTube

Production-ready сервис загрузки медиа по ссылке: Telegram-бот + адаптивное веб-приложение + Telegram Mini App + backend API + очередь фоновых задач + downloader workers + временное хранилище + админка. Источники не ограничены YouTube — архитектура расширяемая (yt-dlp, gallery-dl, прямые файлы и др.).

> Продолжение прежнего монолитного скрипта ShareTube. Что найдено и перенесено — см. [LEGACY_AUDIT.md](LEGACY_AUDIT.md).

## Возможности

- Приём ссылки из бота, с веб-страницы или из Telegram Mini App.
- Нормализация и SSRF-безопасная проверка URL, определение источника и типа контента (видео, Shorts/Reels/TikTok, аудио, фото, карусель, смешанная публикация, плейлист, трансляция).
- Получение метаданных без полной загрузки: название, автор, длительность, превью, форматы, разрешения, кодеки, приблизительный размер, число элементов.
- Выбор только реально доступных вариантов качества (Авто / 1080p / 720p / 480p / мин. размер / оригинал / только аудио).
- Фоновая очередь с прогрессом, этапами, отменой, повтором и историей.
- Умная доставка по **фактическому** размеру: обычный Bot API → Local Bot API → снижение качества / только аудио / временная подписанная ссылка. Кэш `file_id` для повторной отправки без перезагрузки.
- Фото и карусели: одиночное фото, альбомы `sendMediaGroup` (по 10), разбиение больших подборок, ZIP + ссылка.
- Обязательная маршрутизация всех загрузок через прокси/Xray (никогда — напрямую).
- Админка: задания, очередь, ошибки, пользователи, сеть/прокси, Xray, cookies, источники, версии инструментов, хранилище, логи, очистка.

## Стек

Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis, ARQ (очередь), python-telegram-bot (async), yt-dlp, gallery-dl, FFmpeg/FFprobe.
Frontend: React + TypeScript + Vite, адаптивная вёрстка, PWA, Telegram Mini Apps API, SSE-прогресс.
Инфраструктура: Docker Compose, Coolify + Traefik (домен и HTTPS), Xray sidecar, structured JSON-логи.

## Структура репозитория

```
apps/backend      FastAPI-приложение, модели, миграции, worker (ARQ), Telegram-бот
apps/frontend     React + Vite (веб, PWA, Mini App)
apps/bot          (бот запускается из apps/backend/app/tgbot.py тем же образом)
workers/downloader (ARQ worker — app.worker в том же образе)
services/xray     Xray sidecar (генерация конфига из URI, SOCKS5/HTTP inbound)
services/telegram-bot-api  Опциональный Local Bot API (официальный образ)
infra             dev/coolify overlay для docker-compose
scripts           first-run, deploy, backup, restore, update-tools, cleanup, health-check
tests             pytest: SSRF, filenames, delivery, initData, signed urls, extractor, storage, queue, API
docs              инструкции (бот, api_id/hash, Local Bot API, домен/HTTPS, proxy, cookies, восстановление)
legacy            копии старого скрипта (секреты отредактированы)
```

## Быстрый старт (локально / на сервере)

```bash
cp .env.example .env
# отредактируйте BOT_TOKEN, TELEGRAM_ADMIN_IDS, XRAY_OUTBOUND_URI, SECRET_KEY, POSTGRES_PASSWORD
bash scripts/first-run.sh          # первый запуск: сгенерирует часть секретов, соберёт и поднимет стек
```

Прямой доступ для теста: `http://<IP>:8989`. Production — через домен (см. ниже).

### Компоненты docker-compose

`postgres`, `redis`, `xray`, `app` (FastAPI + статика фронта, порт 8989), `worker` (ARQ), `bot` (python-telegram-bot), опционально `telegram-bot-api`.
Наружу публикуется только `app`. PostgreSQL, Redis, Xray и Local Bot API в интернет не выставляются.

### Домен и HTTPS (Coolify Traefik)

```bash
docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d
```
Overlay навешивает Traefik-лейблы и подключает `app` к сети `coolify` → `https://sharetube.appswire.ru` с автоматическим Let's Encrypt. Подробнее — [docs/domain-https.md](docs/domain-https.md).

## Тесты

```bash
cd tests && python -m pytest -q      # 51 тест: SSRF, delivery routing, initData, storage TTL, API и др.
```
В обычных тестах не используются реальные токены и cookies.

## Документация

- [Создание Telegram-бота](docs/telegram-bot.md)
- [api_id и api_hash](docs/api-id-hash.md)
- [Local Bot API](docs/local-bot-api.md)
- [Домен и HTTPS](docs/domain-https.md)
- [HTTP/SOCKS proxy и Xray](docs/proxy.md)
- [Cookies profiles](docs/cookies.md)
- [Восстановление после сбоя](docs/recovery.md)
- [Архитектура](docs/architecture.md)
- [Эксплуатация (OPERATIONS)](OPERATIONS.md), [Безопасность (SECURITY_NOTES)](SECURITY_NOTES.md)

## Безопасность

SSRF-защита, блокировка приватных/loopback/link-local/metadata адресов, повторная проверка после DNS и на каждом redirect, безопасные имена файлов, защита от path traversal, rate limiting, квоты, ограничение одновременных заданий, CSRF/сессии, валидация Telegram initData, шифрование cookies/proxy-секретов, маскирование секретов в логах и API. Подробнее — [SECURITY_NOTES.md](SECURITY_NOTES.md).

Сервис не обходит DRM, платные подписки, приватные аккаунты и иные механизмы контроля доступа. Прокси/Xray используются только как сетевой маршрут к общедоступному источнику.
