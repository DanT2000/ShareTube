# Восстановление после сбоя (runbook)

Практический сценарий действий при инцидентах: логи, здоровье сервисов, бэкап/restore БД,
поведение заданий при перезапуске, очистка хранилища, ротация утёкших секретов, полная пересборка,
перезапуск Coolify/Traefik.

Все команды выполняются из **корня проекта на сервере** (там, где `docker-compose.yml`).

---

## 1. Быстрый осмотр

```bash
# состояние всех контейнеров
docker compose ps

# сводный health-probe (app /health и /health/ready, redis, postgres, xray)
bash scripts/health-check.sh
```

`scripts/health-check.sh` проверяет:
`docker compose ps`, `GET /health`, `GET /health/ready`, `redis-cli ping`, `pg_isready`, доступность
`xray:1080` из worker.

---

## 2. Логи

```bash
docker compose logs -f app       # FastAPI + раздача фронта
docker compose logs -f worker    # ARQ worker (загрузки)
docker compose logs -f bot       # Telegram-бот
docker compose logs -f xray      # sidecar маршрутизации

# последние N строк без «хвоста»
docker compose logs --tail=200 worker

# фильтры по событиям маршрутов/ошибок
docker compose logs worker | grep -E 'no_route|route_failover|download_job_error'
```

Логи структурированные (JSON, `LOG_JSON=true`). Секреты (токен бота, cookies, пароль прокси,
presigned-URL, initData) в логах **маскируются**.

---

## 3. Перезапуск сервисов

Политика рестарта у всех сервисов — `restart: unless-stopped` (Docker сам поднимает упавшие
контейнеры).

```bash
# перезапустить один сервис
docker compose restart worker

# пересоздать сервис с текущим .env
docker compose up -d worker

# перезапустить всё
docker compose up -d
```

---

## 4. Что происходит с заданиями «в полёте» при перезапуске

- Каждое активное задание обновляет **heartbeat** (`download_jobs.heartbeat_at`,
  `started_at`) во время работы.
- Cron **`recover_stale_cron`** (в worker, каждые 10 минут) переводит в `failed` задания, которые
  «зависли» в статусах `downloading/merging/converting/uploading` дольше
  `JOB_TIMEOUT_MINUTES + 5` минут (например, worker упал в процессе). Ошибка — `timeout`.
- Такие задания можно **повторить** (retry) из истории/бота — файлы и метаданные не теряются, БД
  хранит состояние.
- Отмена задания идёт через Redis-флаг; при рестарте незавершённые временные каталоги
  `TMP_DIR/job_<id>` очищаются (`cleanup_stale_tmp`).

Cron-обслуживание worker (`apps/backend/app/worker.py`):

| Cron | Периодичность | Что делает |
|---|---|---|
| `cleanup_cron` | каждые 15 мин | удаляет истёкшие ссылки, вытесняет файлы сверх лимита, чистит tmp |
| `recover_stale_cron` | каждые 10 мин | фейлит зависшие задания (`timeout`) |

---

## 5. Бэкап и восстановление БД

### Бэкап

```bash
bash scripts/backup.sh
```

- Делает `pg_dump` в `./backups/db_<STAMP>.sql.gz` (gzip).
- Также сохраняет размер тома хранилища в `storage_size_<STAMP>.txt`.
- Ротация: хранит последние **14** дампов.
- **Секреты (`.env`) намеренно не бэкапятся** — их владелец хранит отдельно.

Каталог назначения можно переопределить: `BACKUP_DIR=/mnt/backups bash scripts/backup.sh`.

### Восстановление

```bash
bash scripts/restore.sh ./backups/db_20260717_030000.sql.gz
```

- Скрипт **перезапишет текущую БД** — спросит подтверждение (введите `yes`).
- После восстановления автоматически применяются миграции (`alembic upgrade head`).

> Файлы медиа (том `st_storage`) — временные (TTL ссылок 24 ч, вытеснение по `MAX_STORAGE_GB`).
> Полноценно бэкапится **состояние в PostgreSQL**; сами медиафайлы восстановлению не подлежат и не
> критичны (задание можно повторить).

---

## 6. Очистка хранилища

```bash
bash scripts/cleanup.sh
```

Запускает в контейнере `app`:

- `cleanup_expired` — удаление истёкших ссылок/файлов,
- `enforce_storage_cap` — вытеснение самых старых файлов сверх `MAX_STORAGE_GB`,
- `cleanup_stale_tmp` — удаление «осиротевших» временных каталогов.

Выводит `expired=<N> freed_bytes=<N> stale_tmp=<N>`. То же самое доступно из админки
(`POST /api/admin/cleanup`) и выполняется по расписанию (`cleanup_cron`).

---

## 7. Ротация утёкшего секрета

Если секрет мог «засветиться» — меняйте немедленно.

### Токен бота

1. @BotFather → `/mybots → <бот> → API Token → Revoke current token`.
2. Обновите `BOT_TOKEN` в `.env`.
3. `docker compose up -d bot`.

### SECRET_KEY (подписи ссылок, сессии, ключ шифрования)

`SECRET_KEY` используется для подписи скачиваемых ссылок/сессий и как основа шифрования секретов в БД.

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(48))"
```

1. Впишите новое значение в `SECRET_KEY`.
2. `docker compose up -d app worker bot`.

> Внимание: смена `SECRET_KEY` инвалидирует **действующие подписанные ссылки и админ-сессии**, а
> также ключ Fernet — ранее зашифрованные cookies/прокси-профили перестанут расшифровываться, их
> нужно **пересоздать** в админке. Планируйте смену как разовую операцию с последующей переливкой
> профилей.

### Прокси / Xray

- Заведите новый профиль в админке (**Настройки → Сеть и прокси**), сделайте его primary, старый
  удалите. Секреты в БД зашифрованы; в env обновите `XRAY_OUTBOUND_URI`/`XRAY_CONFIG_JSON` при
  необходимости и перезапустите `xray`.

### Пароль PostgreSQL

1. Смените пароль в БД и в `.env` (`POSTGRES_PASSWORD`, а также в `DATABASE_URL`/`DATABASE_URL_SYNC`).
2. `docker compose up -d`.

> После передачи проекта владелец обязан **перевыпустить все временно предоставленные секреты**
> (bot token, прокси, Xray, SSH, Coolify token) — см. `SECURITY_NOTES.md`.

---

## 8. Пересборка с нуля

```bash
# пересобрать образы и накатить миграции
bash scripts/deploy.sh
```

`scripts/deploy.sh`: `docker compose build` → поднимает postgres/redis → `alembic upgrade head`
(через `docker compose run --rm app migrate`) → `docker compose up -d --remove-orphans` → ждёт
health до 90 c.

**Полная переустановка стека** (данные в томах сохраняются):

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Уничтожить и тома тоже** (ВНИМАНИЕ: удалит БД, Redis, файлы, tmp, состояние bot-api):

```bash
docker compose down -v      # удаляет st_pgdata, st_redis, st_storage, st_tmp, st_botapi
bash scripts/first-run.sh   # заново
```

Первый запуск на чистом сервере:

```bash
bash scripts/first-run.sh   # создаст .env из примера, сгенерирует SECRET_KEY/пароль PG
# отредактируйте BOT_TOKEN, TELEGRAM_ADMIN_IDS, XRAY_OUTBOUND_URI
bash scripts/first-run.sh   # повторный запуск: сборка, миграции, старт
```

---

## 9. Перезапуск домена/HTTPS (Coolify / Traefik)

Если перестал открываться домен/сертификат, а контейнеры ShareTube здоровы — проблема на уровне
прокси Coolify (Traefik). ShareTube-часть:

```bash
# пересоздать app с Traefik-лейблами (overlay)
docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d app

# проверить, что app в сети coolify
docker inspect $(docker compose ps -q app) --format '{{json .NetworkSettings.Networks}}'
```

Проверка HTTPS — см. [docs/domain-https.md](domain-https.md) (раздел «Проверка»). Перезапуск самого
Traefik/Coolify-proxy выполняется средствами Coolify (это общий для сервера компонент — не трогайте
чужие приложения). Пока домен недоступен — рабочий fallback: `http://188.18.55.140:8989` +
`TELEGRAM_USE_WEBHOOK=false`.

---

## Таблица «инцидент → действие»

| Инцидент | Первое действие |
|---|---|
| Бот молчит | `docker compose logs -f bot`; проверить `BOT_TOKEN`; при webhook — HTTPS |
| Задания падают `NO_ROUTE` | `bash scripts/health-check.sh`; проверить/включить профиль в админке |
| Кончилось место | `bash scripts/cleanup.sh`; снизить `MAX_STORAGE_GB` при нужде |
| Зависшие задания | подождать `recover_stale_cron` (≤10 мин) или повторить из истории |
| Потеря БД | `bash scripts/restore.sh <дамп>` |
| Утёк секрет | раздел 7 (ротация) |
| Не открывается домен | раздел 9 + [docs/domain-https.md](domain-https.md) |
