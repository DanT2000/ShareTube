# Создание Telegram-бота для ShareTube

Этот документ описывает, как создать бота через **@BotFather**, получить токен, настроить
имя/описание/команды, режим приватности и как прописать токен в `.env`. Также — как узнать
свой числовой Telegram ID для доступа в админку.

> Все значения ниже — примеры. Реальный токен нигде не коммитится в Git и хранится только в `.env`
> (см. `.env.example`). В логах и API токен маскируется.

---

## 1. Создать бота через @BotFather

1. Откройте в Telegram диалог с [@BotFather](https://t.me/BotFather).
2. Отправьте команду `/newbot`.
3. Укажите **отображаемое имя** бота (например, `ShareTube`).
4. Укажите **username** — он обязан заканчиваться на `bot` (например, `sharetube_bot`).
5. BotFather пришлёт сообщение с **токеном** вида:

   ```
   123456789:AAExampleExampleExampleExampleExample
   ```

   Это и есть значение для `BOT_TOKEN`. **Никому не показывайте его и не коммитьте в Git.**

Если бот уже создан, но токен утерян/скомпрометирован — в @BotFather:
`/mybots → выбрать бота → API Token → Revoke current token` (старый токен сразу перестанет работать).

---

## 2. Имя, описание, картинка

В @BotFather командой `/mybots → <бот> → Edit Bot`:

- **Edit Name** — отображаемое имя.
- **Edit Description** — текст на экране до первого запуска (кнопка «Запустить»). Пример:

  > ShareTube — скачивание видео, аудio и фото по ссылке. Пришлите ссылку — получите файл.

- **Edit About** — короткий текст в профиле бота.
- **Edit Botpic** — аватар.

Либо отдельными командами: `/setname`, `/setdescription`, `/setabouttext`, `/setuserpic`.

---

## 3. Команды бота (/start, /history)

ShareTube-бот использует набор команд. Задайте их через `/setcommands` (или
`/mybots → <бот> → Edit Bot → Edit Commands`). Отправьте BotFather такой список:

```
start - Запустить бота и получить инструкцию
history - История ваших загрузок
```

После этого команды появятся в меню «/» у пользователей.

> Обработчики этих команд реализованы в боте (`apps/backend/app/tgbot.py`). `/start` присылает
> приветствие и предлагает отправить ссылку; `/history` показывает последние задания пользователя.

---

## 4. Режим приватности (Privacy Mode)

По умолчанию у ботов включён **Privacy Mode** — в группах бот видит только сообщения-команды и
ответы на свои сообщения, но не обычные тексты. ShareTube в личке работает всегда; для групп
поведение зависит от того, как вы хотите принимать ссылки:

- **Личные чаты** — приватность не влияет, ссылки принимаются всегда.
- **Группы, где бот должен ловить любые ссылки** — отключите приватность:
  `/mybots → <бот> → Bot Settings → Group Privacy → Turn off`
  (либо `/setprivacy → Disable`). После смены режима **удалите и заново добавьте бота в группу**,
  иначе изменение не применится.
- Если бот в группах не нужен — приватность можно оставить включённой, а также запретить
  добавление в группы: `Bot Settings → Allow Groups? → Turn off`.

---

## 5. Прописать токен в .env

Откройте `.env` (создаётся из `.env.example`) и заполните:

```dotenv
BOT_TOKEN=123456789:AAExampleExampleExampleExampleExample
BOT_USERNAME=sharetube_bot
```

- `BOT_TOKEN` — токен из @BotFather.
- `BOT_USERNAME` — username **без** символа `@`. Он используется во фронтенде для
  Telegram Login Widget и в ссылках на бота.

После изменения `.env` перезапустите бота:

```bash
docker compose up -d bot
# или полностью:
bash scripts/deploy.sh
```

---

## 6. Ваш числовой Telegram ID (для админки)

Доступ в админку `/admin` разрешён только Telegram-аккаунтам, перечисленным в
`TELEGRAM_ADMIN_IDS`. Нужен **числовой** id (не username).

1. Откройте [@userinfobot](https://t.me/userinfobot) и нажмите «Start».
2. Бот пришлёт ваш `Id` — целое число (например, `842001234`).
3. Впишите его в `.env` (несколько id — через запятую, без пробелов):

   ```dotenv
   TELEGRAM_ADMIN_IDS=842001234,791005678
   ```

4. Перезапустите приложение:

   ```bash
   docker compose up -d app bot
   ```

Логин в админку — через Telegram Login Widget на странице `/admin`. Аккаунты вне списка
получают `403 not an admin`.

---

## 7. Webhook или long-polling

ShareTube поддерживает оба режима, переключение — через `.env`:

```dotenv
# false = long-polling (по умолчанию), true = webhook
TELEGRAM_USE_WEBHOOK=false
TELEGRAM_WEBHOOK_SECRET=<случайная_строка>
```

- **Long-polling** (`TELEGRAM_USE_WEBHOOK=false`) — бот сам опрашивает Telegram. Работает
  **без домена и HTTPS**, подходит для запуска на `http://<IP>:8989` и при недоступном SSL.
  Рекомендуется как стартовый режим.
- **Webhook** (`TELEGRAM_USE_WEBHOOK=true`) — Telegram сам шлёт апдейты на публичный HTTPS-URL.
  **Требует работающего HTTPS** на `https://sharetube.appswire.ru` (валидный сертификат
  Let's Encrypt). Включайте webhook только после того, как HTTPS проверен (см.
  [docs/domain-https.md](domain-https.md)). `TELEGRAM_WEBHOOK_SECRET` — секрет для проверки
  подлинности входящих запросов Telegram.

> Не включайте webhook, пока не убедились, что `curl -I https://sharetube.appswire.ru` возвращает
> валидный сертификат. Иначе бот перестанет получать сообщения.

Один и тот же токен нельзя одновременно использовать в polling и webhook — при переключении
режим меняется автоматически при старте контейнера `bot`.

---

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| Бот не отвечает на `/start` | Проверьте `BOT_TOKEN`, `docker compose logs -f bot`. |
| В группе не видит ссылки | Не отключён Privacy Mode, либо бот не переприглашён в группу. |
| «not an admin» в `/admin` | Ваш id не в `TELEGRAM_ADMIN_IDS` (нужен числовой id из @userinfobot). |
| Webhook не работает | Нет валидного HTTPS. Вернитесь на polling (`TELEGRAM_USE_WEBHOOK=false`). |
| Токен «засветился» | Revoke в @BotFather, обновите `BOT_TOKEN`, перезапустите `bot`. |
