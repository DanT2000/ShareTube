# Cookies profiles

Некоторым источникам (YouTube, Instagram, VK и др.) для доступа к контенту, к которому у
пользователя **есть законный доступ**, нужны cookies (авторизованная сессия, подтверждение возраста,
región). ShareTube хранит их в виде **cookie-профилей**, привязанных к источнику.

> **Юридически.** Cookies используются только для доступа к контенту, к которому у владельца
> аккаунта есть законное право. ShareTube **не обходит** платные подписки (paywall), DRM, приватный
> контент чужих аккаунтов и иные механизмы контроля доступа. См. `SECURITY_NOTES.md`.

---

## Формат: Netscape cookies.txt

Cookies загружаются в **формате Netscape** (`cookies.txt`) — тот же, что понимает yt-dlp. Файл
выглядит так (поля через табуляцию):

```
# Netscape HTTP Cookie File
.youtube.com    TRUE    /    TRUE    1780000000    SID    <значение>
.youtube.com    TRUE    /    TRUE    1780000000    HSID   <значение>
```

Как получить файл:

- **yt-dlp** — экспорт из вашего браузера:

  ```bash
  yt-dlp --cookies-from-browser chrome --cookies cookies.txt --skip-download "https://www.youtube.com/watch?v=..."
  ```

  (вместо `chrome` — `firefox`, `edge`, `brave` и т.п.)
- **Расширение браузера** для экспорта cookies в формате Netscape (например, «Get cookies.txt»),
  затем сохранить как `cookies.txt`.

Экспортируйте cookies **для конкретного источника** (домена), чтобы профиль был узким и не содержал
лишних сессий.

---

## Загрузка через админку

Раздел **«Cookies profiles»** (фронт: `apps/frontend/src/components/admin/CookiesPanel.tsx`).

Эндпоинты (`apps/backend/app/routers/admin.py`):

| Действие | Эндпоинт |
|---|---|
| Список профилей (без данных cookies) | `GET /api/admin/cookies` |
| Создать/обновить профиль | `POST /api/admin/cookies` |

Параметры создания/обновления `POST /api/admin/cookies`:

- `source` — источник: `youtube`, `instagram`, `vk`, `tiktok`, ...
- `name` — метка профиля (например, `main` или `account-2`).
- `cookie_data` — содержимое файла `cookies.txt` (текст в формате Netscape).

Профиль **уникален по паре** (`source`, `name`): повторная загрузка обновляет существующий.
Пример (обычно выполняется из UI, но можно и curl из админ-сессии):

```bash
curl -X POST "https://sharetube.appswire.ru/api/admin/cookies" \
  --cookie "st_admin=<сессия_админа>" \
  --data-urlencode "source=youtube" \
  --data-urlencode "name=main" \
  --data-urlencode "cookie_data@cookies.txt"
```

---

## Хранение и приватность

- Cookies **шифруются в БД** (Fernet, `cookie_profiles.encrypted_data`). Ключ — `SECRET_KEY`.
- Данные cookies **никогда не возвращаются** через API. `GET /api/admin/cookies` отдаёт только
  метаданные: `source`, `name`, `enabled`, `health_status`, `last_checked_at`, `has_data`.
- Cookies **не пишутся в логи** (в аудит-лог попадает только факт `upsert_cookie` с меткой
  `source:name`, без содержимого).
- Cookies **не коммитятся в Git** (исторический `cookies.txt` в корне исключён из репозитория).
- При скачивании worker расшифровывает профиль во **временный файл** в `TMP_DIR`, передаёт его
  экстрактору и **удаляет сразу после** использования (`apps/backend/app/worker.py`, `_cookies_for`).

---

## Здоровье профиля

У каждого профиля есть:

- `health_status` — `ok` | `failing` | `unknown` (после загрузки — `unknown`, пока не проверен).
- `last_checked_at` — дата последней проверки.
- `enabled` — используется ли профиль при загрузках.
- Привязка к источнику (`source`) — worker берёт **включённый** профиль этого источника
  автоматически.

Cookies со временем **протухают** (сессия истекает). Если для источника начались ошибки авторизации
(`auth_required`), обновите профиль администратором — заново экспортируйте `cookies.txt` и загрузите
через тот же `POST /api/admin/cookies` (тем же `source`+`name`).

---

## Частые случаи

| Ситуация | Что делать |
|---|---|
| YouTube просит подтвердить, что «вы не бот» | Загрузите свежий cookie-профиль `youtube`. |
| Instagram: reels/карусель не открываются | Cookie-профиль `instagram` + при необходимости отдельный выход (см. [docs/proxy.md](proxy.md)). |
| `auth_required` в задании | Сессия истекла — обновите cookie-профиль источника. |
| Нужно временно отключить cookies | В админке снимите `enabled` у профиля. |

> ShareTube применяет cookies только как средство доступа к легально доступному пользователю
> контенту. Ответственность за законность использования аккаунтов лежит на владельце.
