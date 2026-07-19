# SECURITY_NOTES — реализованные меры безопасности

Документ перечисляет защитные механизмы ShareTube, где они реализованы, и что владелец обязан
перевыпустить после передачи проекта. Ссылки на код — относительно `apps/backend/app/`.

---

## 1. SSRF-защита и валидация URL

Модуль `security/ssrf.py`. Любая пользовательская ссылка проходит `validate_url()` до постановки в
очередь:

- **Allowlist схем** — разрешены только `http` и `https`; `data:`/`file:`/`ftp:` и прочее
  отклоняются (`scheme`).
- **Блокировка внутренних адресов** — приватные диапазоны, loopback, link-local, multicast,
  reserved, unspecified, IPv6 site-local; распаковка **IPv4-mapped IPv6** и повторная проверка.
- **Cloud metadata** — явный блок `169.254.169.254`, `metadata.google.internal`, `metadata`,
  `100.100.100.200` (`blocked_host`).
- **Проверка после DNS** — резолв хоста и проверка **каждого** полученного IP (защита от DNS-rebinding).
- **Повторная проверка на редиректах** — `validate_redirect()` применяет те же правила к каждому
  `Location` (в загрузчике ограничение `MAX_REDIRECTS`).
- **IDN-нормализация** — приведение хоста к punycode (`encode("idna")`) против homograph-атак.
- **Allow/deny домены** — `DOMAIN_ALLOWLIST` / `DOMAIN_DENYLIST` (совпадение по хосту и родительским
  доменам).
- **Ограничение длины URL** — `MAX_URL_LENGTH` (по умолчанию 2048).

Пользователю возвращается безопасное русскоязычное сообщение, без трассировки.

---

## 2. Безопасные имена файлов и path traversal

Модуль `security/filenames.py`:

- `sanitize_filename()` — срезает директорийную часть (`/` и `\`), NFKC-нормализация, удаление
  управляющих символов, схлопывание `..`, обрезка по длине, guard для зарезервированных имён
  (`CON/PRN/AUX/NUL`).
- **Нейтрализация исполняемых расширений** — `BLOCKED_EXTENSIONS` (`.exe .sh .bat .cmd .com .msi
  .scr .dll .so .php .py .pl .rb .jar .apk .deb .rpm .ps1`) получают суффикс `.bin` и никогда не
  трактуются как медиа.
- `safe_join()` — гарантирует, что итоговый путь остаётся внутри базового каталога (`realpath` +
  префиксная проверка), иначе `path traversal detected`.
- Внутри хранилища файлы адресуются **непрозрачными токенами** (`stored_files.opaque_token`), а не
  угадываемыми именами.

---

## 3. Rate limiting, квоты, лимиты параллелизма

- **Rate limit** — `security/ratelimit.py`, `RATE_LIMIT_PER_MINUTE` (по умолчанию 30).
- **Квоты пользователя** — `MAX_ACTIVE_JOBS_PER_USER`, `MAX_QUEUED_JOBS_PER_USER`,
  а также `users.quota_daily_jobs` / `quota_daily_bytes` (настраиваются админом).
- **Глобальные лимиты** — `MAX_GLOBAL_DOWNLOADS`, `MAX_GLOBAL_TRANSCODES` через Redis-семафоры
  (`worker.py`, `RedisSemaphore`); `MAX_PLAYLIST_ITEMS`, `JOB_TIMEOUT_MINUTES`.
- **Лимиты размера/длительности** — `MAX_DOWNLOAD_SIZE_MB` (10000), проверка **фактического**
  размера при доставке.

---

## 4. Подписанные ссылки с TTL и защита от перебора

- Токены ссылок — `security/signed_urls.py` (`itsdangerous.URLSafeTimedSerializer`, отдельные salt
  для download и admin-сессий, ключ `SECRET_KEY`).
- **TTL** — `download_links.expires_at` (`DOWNLOAD_LINK_TTL_HOURS=24`), опциональный лимит числа
  скачиваний (`max_downloads`), возможность `revoked`.
- **Brute-force guard** — `routers/download.py`: блокировка по IP при частых промахах
  (`is_locked_out`, threshold 30 → `429`), отклонение слишком коротких токенов (`< 16` символов).
- Range-запросы поддержаны, но всё под проверкой подписи/срока/лимита.

---

## 5. Валидация Telegram (initData / Login Widget)

Модуль `security/telegram_auth.py`. **Никогда** не доверяем `user id` с фронтенда — проверяется HMAC:

- **Mini App initData** — `secret_key = HMAC-SHA256("WebAppData", bot_token)`,
  `hash = HMAC-SHA256(secret_key, data_check_string)`; сверка `hmac.compare_digest`, контроль
  «свежести» `auth_date` (`MAX_AUTH_AGE_SECONDS = 24h`).
- **Login Widget** (админка) — `secret_key = SHA256(bot_token)`, аналогичная сверка и контроль
  возраста подписи.
- В админку пускаются только id из `TELEGRAM_ADMIN_IDS` (`routers/admin.py`, иначе `403`).

---

## 6. Шифрование секретов «в покое» (Fernet)

Модуль `security/crypto.py` (ключ из `SECRET_KEY`):

- **Cookies** — `cookie_profiles.encrypted_data` (Fernet). Не возвращаются через API, не логируются,
  не коммитятся.
- **Прокси/Xray конфиги** — `proxy_profiles.encrypted_config` (Fernet). В API — только маскированные
  `display_meta` (протокол + обрезанные host/port, без пароля/URI).

---

## 7. Маскирование секретов в логах

Никогда не попадают в логи в открытом виде:

- **токен бота** (в админке — только `token_fingerprint` = первые 8 hex от SHA-256);
- **cookies** (в аудит только `source:name`, без содержимого);
- **пароль/URL прокси и Xray URI/JSON** (логируется имя профиля, `kind`, статус, задержка);
- **presigned URL** объектного хранилища;
- **Telegram initData**.

Логи структурированные (`LOG_JSON=true`, `logging_config.py`).

---

## 8. Аутентификация админа и аудит

- Сессия админа — подписанная кука `st_admin` (`httponly`, `secure` при HTTPS, `samesite=lax`,
  TTL `ADMIN_SESSION_TTL_HOURS`).
- Все админ-эндпоинты — `Depends(require_admin)`.
- **Аудит-лог** (`audit_logs`) фиксирует действия: `create/toggle/delete` профилей, `block_user`,
  `set_quota`, `upsert_cookie`, `cancel_job`, `delete_file`, `cleanup` — с actor/target/detail/ip,
  но **без секретов**.

---

## 9. CORS и security-заголовки

- **CORS** — `CORS_ORIGINS` (по умолчанию `https://sharetube.appswire.ru`).
- Security-заголовки (CSP/усиления) и защита cookie-сессий на уровне приложения; за TLS и редирект
  HTTP→HTTPS отвечает Traefik (см. [docs/domain-https.md](docs/domain-https.md)).
- Наружу опубликован только сервис `app`; postgres/redis/xray/local-bot-api изолированы в
  Docker-сети.

---

## 10. Сетевая политика загрузок

`OUTBOUND_REQUIRED=true`: загрузки идут **только** через настроенный профиль (HTTP proxy или Xray).
«proxy failed» **не означает** «идти напрямую» — при отсутствии маршрута задание завершается
`NO_ROUTE`. Xray дополнительно блокирует туннелирование к приватным IP (`geoip:private → blackhole`).
Подробнее — [docs/proxy.md](docs/proxy.md).

---

## Что нужно перевыпустить владельцу после передачи

Все временно предоставленные секреты считаются **скомпрометированными по факту передачи** и должны
быть **перевыпущены владельцем**:

- [ ] **Токен бота** — Revoke в @BotFather, новый `BOT_TOKEN` в `.env`.
- [ ] **`SECRET_KEY`** — сгенерировать заново (`python3 -c "import secrets;print(secrets.token_urlsafe(48))"`);
      учесть, что это инвалидирует действующие ссылки/сессии и ключ шифрования (cookies/прокси-профили
      пересоздать в админке).
- [ ] **Пароль PostgreSQL** — `POSTGRES_PASSWORD` + строки `DATABASE_URL`/`DATABASE_URL_SYNC`.
- [ ] **Прокси-профили** — сменить учётные данные HTTP-прокси, пересоздать профиль в админке.
- [ ] **Xray** — новый `XRAY_OUTBOUND_URI`/`XRAY_CONFIG_JSON` (VLESS/Reality ключи и т.п.).
- [ ] **SSH-доступ к серверу** — заменить ключ `sharetube-deploy`, убрать временный парольный доступ.
- [ ] **Coolify token / доступы** — перевыпустить.
- [ ] Проверить, что реального `.env`, `cookies.txt`, `config.txt` нет в Git (только `.example`).

---

## Явные non-goals (что сервис НЕ делает)

- **Не обходит DRM.**
- **Не обходит платные подписки / paywall.**
- **Не получает доступ к приватному контенту чужих аккаунтов.**
- **Не подменяет механизмы контроля доступа.**

Прокси/Xray используются исключительно как **сетевой маршрут** к общедоступному источнику; cookies —
только для контента, к которому у владельца аккаунта есть законный доступ.
