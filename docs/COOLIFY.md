# Установка ShareTube через Coolify

ShareTube разворачивается как **Docker Compose**-ресурс Coolify из git-репозитория. Coolify клонирует репозиторий, собирает образы (backend с фронтендом + Xray) и поднимает весь стек; домен и HTTPS Coolify берёт на себя через свой Traefik.

## Что нужно один раз

1. Репозиторий с кодом (публичный или приватный с deploy key). Ветка с production-кодом и `docker-compose.yml` в корне.
2. Сервер, добавленный в Coolify.
3. Значения секретов: `BOT_TOKEN`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `TELEGRAM_ADMIN_IDS`, `XRAY_OUTBOUND_URI` (или рабочий HTTP-прокси).

## Создание ресурса (UI)

1. Coolify → нужный проект → Environment `production` → **+ New Resource** → **Docker Compose** (Public/Private Repository).
2. Repository: URL репозитория, Branch — ветка с production-кодом.
3. Build Pack: **Docker Compose**, Compose file: `/docker-compose.yml`.
4. **Environment Variables** — задать переменные (см. `.env.example`). Обязательные: `SECRET_KEY`, `POSTGRES_PASSWORD`, `BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`, `XRAY_OUTBOUND_URI`, `PUBLIC_BASE_URL`. Остальные имеют разумные значения по умолчанию.
5. **Domains** — назначить сервису `app` домен (напр. `https://sharetube.appswire.ru`). Coolify сам выпустит Let's Encrypt (нужны открытые 80/443 и корректный DNS).
6. **Deploy**.

## Создание ресурса (API)

```sh
# 1) создать ресурс
curl -X POST https://<coolify>/api/v1/applications/public \
  -H "Authorization: Bearer $COOLIFY_TOKEN" -H "Content-Type: application/json" \
  -d '{"project_uuid":"<proj>","server_uuid":"<srv>","environment_name":"production",
       "git_repository":"https://github.com/<user>/<repo>","git_branch":"main",
       "build_pack":"dockercompose","docker_compose_location":"/docker-compose.yml",
       "name":"sharetube","instant_deploy":false}'

# 2) задать переменные (по одной; поле is_build_time НЕ передавать)
curl -X POST https://<coolify>/api/v1/applications/<app_uuid>/envs \
  -H "Authorization: Bearer $COOLIFY_TOKEN" -H "Content-Type: application/json" \
  -d '{"key":"SECRET_KEY","value":"<...>","is_preview":false}'
# ... повторить для всех переменных из .env.example

# 3) запустить деплой
curl -X POST "https://<coolify>/api/v1/deploy?uuid=<app_uuid>" \
  -H "Authorization: Bearer $COOLIFY_TOKEN"
```

## Важно про env

`docker-compose.yml` не требует файла `.env` внутри сборки: все переменные передаются в сервисы через блок `environment` с подстановкой `${VAR}`. При запуске `docker compose` вручную значения берутся из локального `.env`; в Coolify — из Environment Variables ресурса. Поэтому один и тот же compose работает в обоих режимах.

## Публикация только нужного

Наружу Coolify выставляет только сервис `app` (домен + порт 8989). PostgreSQL, Redis, Xray и Local Bot API остаются во внутренней сети. Не задавайте им домены.

## Установка на другой сервер

Тот же ресурс можно пересоздать на другом сервере: измените `server_uuid` (или в UI выберите другой сервер), задайте `PUBLIC_BASE_URL`/домен нового сервера и `XRAY_OUTBOUND_URI`, нажмите Deploy. Персистентные данные (`st_pgdata`, `st_storage`) создаются заново на новом сервере.

## Проверка после деплоя

```sh
curl -fsS https://<домен>/health          # {"status":"ok"}
curl -fsS https://<домен>/health/ready     # db + redis
```
Логи и статус — во вкладке ресурса в Coolify.
