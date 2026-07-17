# Домен и HTTPS (Coolify Traefik)

ShareTube в production доступен по домену **https://sharetube.appswire.ru**. Домен и TLS выдаёт
существующий на сервере **Traefik** (проксирование Coolify). Прямой тестовый доступ без домена —
`http://<IP>:8989` (приложение слушает порт **8989**).

- Публичный IP сервера: **188.18.55.140**
- Домен: **sharetube.appswire.ru → 188.18.55.140**
- Traefik: entrypoints `http(:80)` / `https(:443)`, certresolver **`letsencrypt`** (HTTP-01),
  docker-провайдер с `exposedbydefault=false`, внешняя сеть **`coolify`**.

---

## 1. DNS

Заведите A-запись:

```
sharetube.appswire.ru.   A   188.18.55.140
```

Проверьте, что имя резолвится в нужный IP **до** выпуска сертификата:

```bash
dig +short sharetube.appswire.ru
# ожидается: 188.18.55.140

nslookup sharetube.appswire.ru
```

Пока DNS не указывает на сервер, Let's Encrypt по HTTP-01 сертификат не выдаст.

---

## 2. Деплой с overlay для Traefik

Базовый `docker-compose.yml` публикует наружу только `app` (порт 8989). Домен и HTTPS
добавляет overlay `infra/docker-compose.coolify.yml` — он навешивает Traefik-лейблы и подключает
`app` к сети `coolify`:

```bash
docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d
```

Что делает overlay (`infra/docker-compose.coolify.yml`):

- подключает `app` к внешней сети `coolify` (там живёт Traefik);
- HTTP-роутер `sharetube-http` на `Host(sharetube.appswire.ru)` c middleware
  `redirectscheme → https` (редирект 80 → 443);
- HTTPS-роутер `sharetube` на том же хосте, `tls=true`, `tls.certresolver=letsencrypt`;
- сервис указывает на внутренний порт контейнера **8989**.

Другие приложения Coolify overlay не трогает.

---

## 3. Как Traefik выпускает сертификат Let's Encrypt

- Используется challenge **HTTP-01**: Let's Encrypt обращается к
  `http://sharetube.appswire.ru/.well-known/acme-challenge/...`.
- Для этого нужны **открытые порты 80 и 443** на сервере и **корректный DNS** (домен → IP сервера).
- Traefik сам получает и продлевает сертификат; отдельных действий не требуется.
- Первый выпуск может занять от нескольких секунд до пары минут после старта контейнера.

---

## 4. Проверка (обязательно перед заявлением «HTTPS работает»)

Не считайте SSL рабочим, пока не проверили командами ниже.

```bash
# 1) HTTPS отвечает и сертификат валиден
curl -I https://sharetube.appswire.ru
# ожидается: HTTP/2 200 (или 3xx на фронт), без ошибок TLS

# 2) Детали сертификата (издатель Let's Encrypt, срок действия, CN)
echo | openssl s_client -connect sharetube.appswire.ru:443 -servername sharetube.appswire.ru 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates

# 3) Редирект HTTP -> HTTPS
curl -sSI http://sharetube.appswire.ru | grep -i -E 'HTTP/|location'
# ожидается: 301/308 и Location: https://sharetube.appswire.ru/...

# 4) health эндпоинт через домен
curl -fsS https://sharetube.appswire.ru/health && echo OK
```

**Признаки успеха:**

- `curl -I https://...` возвращает `HTTP/2 200/3xx` **без** `SSL certificate problem`;
- издатель сертификата — `Let's Encrypt` (или `R3`/`E1` и т.п.), срок действия не истёк;
- HTTP отдаёт редирект на HTTPS;
- нет **mixed content** (все ресурсы фронта грузятся по `https://` — проверьте консоль браузера,
  вкладка Network; в конфиге `CORS_ORIGINS=https://sharetube.appswire.ru` и
  `PUBLIC_BASE_URL=https://sharetube.appswire.ru`).

**Признаки, что сертификата ещё нет / он невалиден:**

- `curl: (60) SSL certificate problem` или `curl: (35)`;
- издатель `TRAEFIK DEFAULT CERT` (самоподписанный) — HTTP-01 не прошёл (проверьте DNS и порты 80/443);
- таймаут на 443 — порт закрыт/недоступен снаружи.

---

## 5. Если HTTPS временно невозможен

Бывает, что домен/сертификат недоступны (DNS ещё не распространился, закрыт 80/443, проблемы у
провайдера). В этом случае:

1. **Используйте прямой доступ** без TLS:

   ```
   http://188.18.55.140:8989
   ```

   Приложение полностью работоспособно по HTTP на порту 8989 (порт свободен на этом сервере —
   см. `SERVER_AUDIT.md`).

2. **Бот — только long-polling.** В `.env`:

   ```dotenv
   TELEGRAM_USE_WEBHOOK=false
   ```

   Long-polling не требует HTTPS и работает при доступе только по IP.

3. **Как понять, что SSL ещё не готов** (точная диагностика):

   ```bash
   curl -Iv https://sharetube.appswire.ru 2>&1 | grep -i -E 'issuer|subject|SSL certificate|expire|HTTP/'
   ```

   Если издатель — `TRAEFIK DEFAULT CERT` или есть `SSL certificate problem` — сертификат **не выпущен**.

> **Не заявляйте, что «SSL работает», пока `curl -I https://sharetube.appswire.ru` не вернёт валидный
> ответ с сертификатом Let's Encrypt.** До этого момента считайте рабочим только
> `http://188.18.55.140:8989` + long-polling.

---

## 6. Webhook Telegram — только при рабочем HTTPS

Telegram доставляет webhook **только на валидный HTTPS-URL**. Поэтому включайте webhook строго
после того, как раздел 4 пройден:

```dotenv
TELEGRAM_USE_WEBHOOK=true
TELEGRAM_WEBHOOK_SECRET=<случайная_строка>
PUBLIC_BASE_URL=https://sharetube.appswire.ru
```

Затем:

```bash
docker compose up -d app bot
```

Если позже HTTPS сломается (истёк/отозван сертификат) — временно верните
`TELEGRAM_USE_WEBHOOK=false`, чтобы бот продолжал получать сообщения через polling.

---

## Чек-лист

- [ ] `dig +short sharetube.appswire.ru` = `188.18.55.140`
- [ ] порты 80 и 443 открыты снаружи
- [ ] `docker compose -f docker-compose.yml -f infra/docker-compose.coolify.yml up -d`
- [ ] `curl -I https://sharetube.appswire.ru` → 200/3xx, издатель Let's Encrypt
- [ ] HTTP → HTTPS редирект работает, mixed content отсутствует
- [ ] только теперь: `TELEGRAM_USE_WEBHOOK=true` (при необходимости webhook)
