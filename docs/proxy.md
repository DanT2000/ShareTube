# Исходящая маршрутизация: HTTP/SOCKS proxy и Xray

## Модель маршрутизации (главное правило)

Все загрузки медиа идут **только** через настроенные исходящие профили (outbound). Прямой выход
worker в интернет к медиаисточникам запрещён политикой:

```dotenv
OUTBOUND_REQUIRED=true
```

- **«proxy failed» ≠ «идём напрямую».** Если активный маршрут недоступен, менеджер маршрутов
  пробует резервный профиль; если исправного маршрута нет — задание завершается ошибкой
  **`NO_ROUTE`** (пользователю — понятное сообщение, без прямого выхода).
- Логика выбора маршрута: `apps/backend/app/outbound/manager.py`
  (`resolve_for_source`, `failover_after_error`, `NoRouteError`).
- Порядок выбора профиля: привязанный к источнику → primary → «здоровый» (`last_status=ok`) →
  backup → по приоритету (`priority`).
- Telegram API, PostgreSQL, Redis и внутренние Docker-соединения через прокси/Xray **не** ходят
  (`NO_PROXY=127.0.0.1,localhost,postgres,redis,xray,telegram-bot-api`).

---

## Два типа профилей

Профили хранятся в таблице `proxy_profiles`. Секреты в БД **зашифрованы** (Fernet), в API и логах
— **маскированы** (`display_meta`: протокол + обрезанный host/port, без пароля).

### 1. HttpProxyProfile — HTTP/HTTPS/SOCKS5 прокси

Код: `apps/backend/app/outbound/http_proxy.py`. Форматы URL:

```
http://user:pass@host:port
https://user:pass@host:port
socks5://user:pass@host:port
socks5h://host:port          # DNS резолвится на стороне прокси (рекомендуется)
```

Тип определяется по схеме URL: `socks*` → `kind=socks5`, иначе `kind=http`.

### 2. XrayProfile — туннель через Xray sidecar

Код: `apps/backend/app/outbound/xray.py`. worker обращается к Xray по адресу внутри Docker-сети:

```dotenv
XRAY_SOCKS_URL=socks5h://xray:1080
```

Сам контейнер `xray` (`services/xray/`) поднимает inbound **SOCKS5 :1080** и **HTTP :1081**
(только внутри Docker-сети, наружу не публикуются) и строит клиентский конфиг из **env** при старте:

```dotenv
# services/xray читает ОДНО из двух (в git не попадает):
XRAY_OUTBOUND_URI=            # напр. vless://...@host:443?security=reality&sni=...&pbk=...
XRAY_CONFIG_JSON=             # либо готовый JSON-конфиг Xray целиком
```

Генератор конфига: `services/xray/generate_config.py` — поддерживает `vless://` (в т.ч. Reality/TLS)
и произвольный `XRAY_CONFIG_JSON`.

---

## Управление профилями в админке

Раздел **«Настройки → Сеть и прокси»** (фронт: `apps/frontend/src/components/admin/ProxyPanel.tsx`).
Эндпоинты — `apps/backend/app/routers/admin.py`:

| Действие | Эндпоинт |
|---|---|
| Список профилей (маскированный) | `GET /api/admin/proxies` |
| Создать HTTP/SOCKS профиль | `POST /api/admin/proxies/http` (`{name,url,is_primary,is_backup,priority,bound_sources}`) |
| Создать Xray профиль | `POST /api/admin/proxies/xray` (`{name,config_or_uri,is_primary,is_backup,priority}`) |
| Проверить соединение | `POST /api/admin/proxies/{id}/check` |
| Включить/выключить | `POST /api/admin/proxies/{id}/toggle?enabled=true|false` |
| Назначить primary/backup | `POST /api/admin/proxies/{id}/role?primary=true` или `?backup=true` |
| Удалить | `DELETE /api/admin/proxies/{id}` |

Возможности:

- **Создать** HTTP/SOCKS или Xray профиль.
- **Проверить** (`check`) — активная проверка соединения; сохраняются `last_status` (`ok|failing`),
  `last_latency_ms`, `last_error_category` (например, `CONNECT_TIMEOUT`). Секреты в результат не
  попадают.
- **Включить/выключить** профиль.
- **Назначить primary** (основной — единственный; при назначении primary у остальных снимается) и
  **backup** (резервный для failover).
- **Привязать к источнику** (`bound_sources`, csv: `youtube,tiktok`) — профиль будет
  предпочитаться для этих источников (например, отдельный выход для Instagram).
- **Маскированный показ** — host/port/протокол видны частично, пароль/URI не возвращаются никогда.

---

## Xray: как задать конфигурацию

При создании Xray-профиля в поле `config_or_uri` можно передать:

- **URI**: `vless://...`, `vmess://...`, `trojan://...`, `ss://...` (Shadowsocks);
- **готовый JSON** конфиг Xray (начинается с `{`);
- **subscription URL** (ссылку на подписку).

Обработка при создании (`POST /api/admin/proxies/xray`):

1. **Валидация до применения.** Если передан JSON (строка начинается с `{`), он проверяется
   `validate_xray_config()` **до** сохранения; при ошибке — `400 invalid_xray` с сообщением, профиль
   не создаётся. URI/подписки проходят как есть.
2. **Атомарное переключение.** Xray sidecar генерирует конфиг из env и перезапускается — активный
   маршрут меняется целиком, без «полусостояний».
3. **Откат (rollback).** Если новый конфиг не проходит проверку/не поднимается, остаётся прежний
   рабочий профиль; неисправный не становится активным.

Поддерживаемые протоколы inbound для потребителей (yt-dlp/gallery-dl/прямые загрузки):
**HTTP / HTTPS / SOCKS5**.

---

## Защита от туннелирования во внутреннюю сеть

В конфиге Xray есть правило маршрутизации:

```json
"routing": { "rules": [ { "type": "field", "ip": ["geoip:private"], "outboundTag": "block" } ] }
```

`geoip:private → blackhole` не даёт обратиться через туннель к приватным/внутренним адресам —
дополнительный слой к SSRF-защите приложения (см. `SECURITY_NOTES.md`).

---

## Секреты и логирование

- URL прокси и Xray URI/JSON **шифруются** в БД (`encrypted_config`, Fernet).
- В API отдаётся только `display_meta` (маскированные host/port/protocol, `has_auth`).
- В логах пароли/URI **не печатаются** — только имя профиля, `kind`, источник, статус, задержка.
- В `.env` секреты Xray (`XRAY_OUTBOUND_URI`/`XRAY_CONFIG_JSON`) не коммитятся в Git.

---

## Диагностика

```bash
# доступность Xray SOCKS изнутри worker
docker compose exec -T worker python -c "import socket;socket.create_connection(('xray',1080),3);print('xray ok')"

# проверить активный маршрут выходным IP (пример через SOCKS Xray)
docker compose exec -T worker sh -c 'curl -s --socks5-hostname xray:1080 https://api.ipify.org; echo'

# логи менеджера маршрутов
docker compose logs -f worker | grep -E 'route_selected|route_failover|no_route'
```

| Симптом | Причина |
|---|---|
| Задание падает с `NO_ROUTE` | Нет ни одного исправного профиля. Проверьте/включите профиль, сделайте `check`. |
| `CONNECT_TIMEOUT` у HTTP-прокси | Прокси недоступен/истёк — переключитесь на рабочий (напр. Xray). |
| Instagram даёт `000`/сброс | Выходной IP заблокирован источником — привяжите другой профиль к `instagram` и/или используйте cookies (см. [docs/cookies.md](cookies.md)). |

> Актуальное состояние маршрутов на сервере фиксируется в `NETWORK_AUDIT.md`.
