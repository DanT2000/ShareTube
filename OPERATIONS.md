# OPERATIONS — эксплуатация ShareTube (day-2)

Практические операции сопровождения. Все команды выполняются из **корня проекта на сервере**
(там, где `docker-compose.yml`). Смежные документы: [docs/recovery.md](docs/recovery.md) (аварии),
[docs/proxy.md](docs/proxy.md) (маршруты), [SECURITY_NOTES.md](SECURITY_NOTES.md).

---

## Частые команды

```bash
# статус контейнеров
docker compose ps

# логи по сервису (app / worker / bot / xray / telegram-bot-api)
docker compose logs -f worker
docker compose logs --tail=200 app

# перезапуск одного сервиса
docker compose restart bot

# пересоздать сервис с текущим .env
docker compose up -d app

# войти внутрь контейнера
docker compose exec app sh
docker compose exec worker bash    # если доступен bash

# разовая команда в одноразовом контейнере
docker compose run --rm app <cmd>
```

### Миграции БД

```bash
docker compose run --rm app migrate      # alembic upgrade head
```

(Роль `migrate` определена в `apps/backend/entrypoint.sh`; при старте `app` миграции применяются
автоматически.) Создание новой ревизии — при разработке:

```bash
docker compose exec app alembic revision --autogenerate -m "описание"
docker compose exec app alembic upgrade head
```

### Health

```bash
bash scripts/health-check.sh
curl -fsS http://localhost:8989/health && echo OK
curl -fsS http://localhost:8989/health/ready && echo READY
```

---

## Масштабирование worker-ов

Загрузки обрабатывают контейнеры `worker` (ARQ). Горизонтально:

```bash
docker compose up -d --scale worker=2
```

Учтите ресурсы сервера (см. `SERVER_AUDIT.md`: 3 vCPU, 2 ГиБ RAM — по умолчанию 2 одновременные
загрузки, 1 перекодировка). Реальный параллелизм ограничивают **глобальные семафоры**:

```dotenv
MAX_GLOBAL_DOWNLOADS=3     # одновременных загрузок на весь кластер (Redis-семафор)
MAX_GLOBAL_TRANSCODES=1    # одновременных перекодировок
```

Поэтому запуск лишних worker сверх `MAX_GLOBAL_DOWNLOADS` прироста не даст — сначала поднимайте лимит.

---

## Настройка лимитов через .env

Меняются в `.env`, применяются перезапуском (`docker compose up -d app worker bot`). Текущие
значения видны в админке (`GET /api/admin/settings`, раздел «Настройки»).

| Переменная | Смысл | По умолчанию |
|---|---|---|
| `CLOUD_BOT_SAFE_LIMIT_MB` | Порог отправки в облачный Bot API | 45 |
| `LOCAL_BOT_SAFE_LIMIT_MB` | Порог отправки в Local Bot API | 1900 |
| `MAX_DOWNLOAD_SIZE_MB` | Абсолютный максимум размера загрузки | 10000 |
| `DOWNLOAD_LINK_TTL_HOURS` | Срок жизни подписанной ссылки | 24 |
| `MAX_STORAGE_GB` | Лимит хранилища (вытеснение старых) | 2 |
| `MAX_ACTIVE_JOBS_PER_USER` | Активных заданий на пользователя | 2 |
| `MAX_QUEUED_JOBS_PER_USER` | В очереди на пользователя | 5 |
| `MAX_GLOBAL_DOWNLOADS` | Глобальный лимит загрузок | 3 |
| `MAX_GLOBAL_TRANSCODES` | Глобальный лимит перекодировок | 1 |
| `MAX_PLAYLIST_ITEMS` | Элементов плейлиста | 20 |
| `JOB_TIMEOUT_MINUTES` | Таймаут задания | 120 |
| `RATE_LIMIT_PER_MINUTE` | Rate limit API | 30 |
| `DOWNLOAD_RATE_LIMIT_KBPS` | Ограничение скорости загрузки (0=без) | 0 |

---

## Очистка и бэкап

```bash
# очистка: истёкшие ссылки, вытеснение сверх лимита, stale tmp
bash scripts/cleanup.sh
# то же из админки: POST /api/admin/cleanup

# бэкап БД (gzip в ./backups, хранит 14 последних; .env НЕ бэкапится)
bash scripts/backup.sh

# восстановление БД из дампа (спросит подтверждение, применит миграции)
bash scripts/restore.sh ./backups/db_YYYYMMDD_HHMMSS.sql.gz
```

По расписанию worker сам чистит хранилище (`cleanup_cron`, каждые 15 мин) и фейлит зависшие задания
(`recover_stale_cron`, каждые 10 мин).

---

## Контролируемое обновление yt-dlp / gallery-dl

Инструменты **не** обновляются автоматически при старте. Обновление — осознанно, со smoke-тестом и
откатом:

```bash
bash scripts/update-tools.sh            # по умолчанию сервис worker
bash scripts/update-tools.sh worker
```

Что делает `scripts/update-tools.sh`:

1. печатает текущие версии `yt-dlp`/`gallery-dl` (в лог `./update-tools.log`);
2. `pip install -U yt-dlp gallery-dl` внутри работающего контейнера;
3. **smoke-тест** — запрос метаданных (без загрузки) через настроенный маршрут;
4. если тест **прошёл** — сообщает, что для сохранения версий между пересборками нужно
   **зафиксировать версии в `requirements.txt`** (`apps/backend/requirements.txt`);
5. если тест **упал** — откат: `docker compose restart <service>` возвращает закреплённый в образе
   набор версий, скрипт завершается с ошибкой.

> Обновление внутри контейнера временно — при пересборке образа вернутся версии из
> `requirements.txt`. Чтобы обновление стало постоянным, поднимите версии в `requirements.txt` и
> пересоберите (`bash scripts/deploy.sh`).

### Проверка версий инструментов

- В админке — раздел **«Версии»** (`GET /api/admin/versions`): `yt-dlp`, `gallery-dl`, `ffmpeg`,
  `ffprobe`.
- Из CLI:

  ```bash
  docker compose exec worker sh -c 'yt-dlp --version; gallery-dl --version; ffmpeg -version | head -1'
  ```

---

## Очередь и активные задания

- В админке — **Dashboard** (`GET /api/admin/dashboard`): активные/в очереди/ошибки/выполнено,
  использование хранилища и диска.
- Список заданий: `GET /api/admin/jobs?status=<...>&limit=<...>` (раздел «Задания»).
- Отмена задания: `POST /api/admin/jobs/{job_id}/cancel`.
- Удалить файл задания: `DELETE /api/admin/jobs/{job_id}/file`.
- Состояние очереди/семафоров можно посмотреть в Redis:

  ```bash
  docker compose exec redis redis-cli
  > KEYS sema:*
  > GET sema:downloads
  ```

---

## Блокировка пользователя

Через админку (раздел «Пользователи») или API:

```bash
# заблокировать
curl -X POST "https://sharetube.appswire.ru/api/admin/users/<user_id>/block?blocked=true" \
  --cookie "st_admin=<сессия>"

# разблокировать
curl -X POST "https://sharetube.appswire.ru/api/admin/users/<user_id>/block?blocked=false" \
  --cookie "st_admin=<сессия>"

# индивидуальная дневная квота
curl -X POST "https://sharetube.appswire.ru/api/admin/users/<user_id>/quota?daily_jobs=50" \
  --cookie "st_admin=<сессия>"
```

Заблокированный пользователь не может ставить новые задания. Все действия пишутся в `audit_logs`.

---

## Ротация секретов

Кратко (полностью — [docs/recovery.md](docs/recovery.md) §7, чек-лист владельца —
[SECURITY_NOTES.md](SECURITY_NOTES.md)):

- **Токен бота** — Revoke в @BotFather → `BOT_TOKEN` → `docker compose up -d bot`.
- **`SECRET_KEY`** — новое значение; инвалидирует ссылки/сессии и ключ шифрования (cookies/прокси
  пересоздать в админке).
- **Прокси/Xray** — новый профиль в админке / `XRAY_OUTBOUND_URI` в `.env` → `up -d xray`.
- **Пароль PG** — `POSTGRES_PASSWORD` + `DATABASE_URL*` → `up -d`.

---

## Поведение лимита хранилища

`STORAGE_PROVIDER=local` + `MAX_STORAGE_GB` → при превышении лимита **вытесняются самые старые**
файлы (`enforce_storage_cap`). Плюс истёкшие по TTL ссылки/файлы удаляются (`cleanup_expired`).
Так стек остаётся в рамках диска (на этом сервере свободно немного — см. `SERVER_AUDIT.md`).
Уменьшить/увеличить: правьте `MAX_STORAGE_GB` в `.env`, затем `docker compose up -d app worker` и при
необходимости `bash scripts/cleanup.sh`.

---

## Где лежат данные (Docker volumes)

| Том | Назначение | Монтируется в |
|---|---|---|
| `st_pgdata` | Данные PostgreSQL | postgres |
| `st_redis` | Данные Redis (очередь/состояние) | redis |
| `st_storage` | Готовые медиафайлы `/data/storage` | app, worker, (telegram-bot-api) |
| `st_tmp` | Временные файлы загрузок `/data/tmp` | app, worker |
| `st_botapi` | Состояние Local Bot API | telegram-bot-api |

```bash
docker volume ls | grep st_
docker compose exec app du -sh /data/storage /data/tmp
```

> `docker compose down` тома сохраняет; `docker compose down -v` **удаляет** их (БД, Redis, файлы) —
> используйте осознанно.

---

## Публикация домена/HTTPS

```bash
docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d
```

Проверка сертификата и fallback на `http://188.18.55.140:8989` — см.
[docs/domain-https.md](docs/domain-https.md).
