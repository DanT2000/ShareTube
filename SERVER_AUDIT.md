# SERVER_AUDIT — аудит целевого сервера «107 Apps»

Дата: 2026-07-17

## Идентификация

- Coolify: сервер `107_AppsServer`, uuid `h11mv152fbvw8vb7o7y89ob5`, reachable/usable.
- Хост: `192.168.2.15`, SSH-порт `22222`, пользователь `root` (доступ по ключу `sharetube-deploy`, установлен поверх временного парольного доступа).
- ОС: Linux `Apps` 6.8.12-17-pve (гость Proxmox VE), x86_64.
- Внешний IP (NAT): `188.18.55.140`. DNS: `sharetube.appswire.ru → 188.18.55.140`, там же `coolify.dev.appswire.ru`.

## Ресурсы

| Ресурс | Значение | Вывод |
|---|---|---|
| CPU | 3 vCPU | Лимиты: 1 одновременная перекодировка, 2 одновременные загрузки. |
| RAM | 2.0 GiB (занято ~1.3 GiB чужими сервисами) + 1 GiB swap | Стек ShareTube спроектирован лёгким: один Python-образ на backend/worker/bot, без отдельного nginx. Local Bot API по умолчанию выключен (экономия ~100+ МБ). |
| Диск | 30 GB, свободно 3.2 GB (89% занято) | Docker-образы других приложений — 9.1 GB. Хранилище ShareTube ограничено `MAX_STORAGE_GB` (по умолчанию 2) с вытеснением старых файлов; сборка образов — многоступенчатая, число новых образов минимизировано. |

## Docker

- Docker 29.4.1, Compose v5.1.3.
- Coolify-proxy: Traefik v3.6, порты 80/443 (+8080) — единственная точка входа для доменов.
- Чужие контейнеры (НЕ трогать): coolify-sentinel, shadowcall-* (postgres, api, web, auth-bot), litellm (+db, в crash-loop — чужая проблема, не вмешиваюсь), web/api tgqmle*, cefb3pwbpbl4oe88w4jsx5av, x9f70pxht6i6ydiklkjoryp2, vqffka16o8cs2wmaghlxmdwx, a2zk9n9xniuthpat2ee45qti.
- Занятые порты хоста: 80, 443, 8080 (traefik), 3000, 3091, 8091, 18080, 4000, 6431. **Порт 8989 свободен** — используется для прямого HTTP-доступа к ShareTube.
- В Coolify включён ежедневный docker cleanup (threshold 80%).

## Существующий ShareTube на сервере

Ресурса/контейнеров ShareTube на сервере и в Coolify до начала работ не было (проверено по списку приложений Coolify и `docker ps`). Старый ShareTube работал на другой машине (Windows, каталог `D:\Program\ShareTube` по данным legacy-скрипта).

## Сеть

- Прямой выход в интернет есть (exit IP = 188.18.55.140).
- Предоставленный HTTP-прокси с сервера недоступен (timeout) — см. NETWORK_AUDIT.md.
- Xray VLESS/Reality работает — основной маршрут загрузок.

## Решения, принятые из-за ограничений сервера

1. Один Docker-образ `sharetube-app` для backend, worker и бота (разные команды запуска) — минус два образа на диске.
2. Фронтенд собирается в том же multi-stage build и раздаётся FastAPI — без отдельного nginx-контейнера.
3. PostgreSQL — образ `postgres:16-alpine`, уже присутствующий на сервере (нулевая стоимость по диску).
4. Local Telegram Bot API — полностью поддержан в compose, но по умолчанию отключён (`LOCAL_BOT_API_ENABLED=false`): на 2 GiB RAM его держать постоянно нецелесообразно, а лимита 45 МБ облачного API + подписанных ссылок достаточно.
5. `MAX_STORAGE_GB=2` по умолчанию для этого сервера (вместо исторических 3) — на диске всего 3.2 GB свободно; значение меняется через env/админку.
