# 📋 Language Menu | Меню языка
- [🇬🇧 English](#eu)
- [🇷🇺 Русский](#ru)

---
<a name="eu"></a>
# 🇬🇧 ShareTube — Telegram Bot & Server for YouTube Downloads

ShareTube is a simple Telegram bot with a backend server that downloads YouTube videos and gives direct access to them via links.

## 🚀 Quick Start

1. **Clone the project:**
```bash
git clone https://github.com/your-path/ShareTube.git
```

2. **Go to the folder and give execute permissions to the script:**
```bash
cd ShareTube
chmod +x install.sh
```

3. **Run the installation script:**
```bash
./install.sh
```

4. **After installation:**
- Set your Telegram Bot Token in `main.py`
- Specify your external server IP (`SERVER_IP`)
- Make sure the `downloads/` folder exists and is accessible

5. **The server runs by default on port `5000`.**

---

## 🛡️ Security & Deployment Recommendations

For better **security and convenience**, we highly recommend using **Nginx** with an **SSL certificate from Let's Encrypt** to reverse-proxy access **only** to the necessary folder:

- Nginx proxies `/downloads/` to Flask/FastAPI
- All other paths are blocked
- This ensures users only access video files, not backend logic




---

## 🤖 How It Works

1. User sends a YouTube link to the bot
2. Bot downloads the video
3. If video < 50 MB — it's sent directly via Telegram
4. Otherwise — a download link is provided

---

## 📌 Notes

- Ensure `downloads/` is readable by NGINX (usually `www-data`)
- Update the token if it is revoked
- Chats are saved and auto-cleaned after inactivity

---
<a name="ru"></a>
# 🇷🇺 ShareTube — бот и сервер для скачивания видео с YouTube

ShareTube — это простой в установке Telegram-бот с сервером, позволяющим скачивать видео с YouTube и автоматически отдавать их по ссылке.

## 🚀 Быстрый старт

1. **Склонировать проект:**
```bash
git clone https://github.com/твой-путь/ShareTube.git
```

2. **Перейти в папку и дать права на скрипт установки:**
```bash
cd ShareTube
chmod +x install.sh
```

3. **Запустить установку:**
```bash
./install.sh
```

4. **После установки:**
- Установить свой токен бота в `main.py`
- Указать внешний IP сервера (`SERVER_IP`)
- Убедиться, что папка `downloads/` существует и доступна

5. **Сервер запускается на порту `5000` по умолчанию.**

---

## 🛡️ Рекомендации по безопасности и развёртыванию

Для безопасности и удобства мы **настоятельно рекомендуем** использовать **Nginx** в связке с **Let's Encrypt сертификатом** и перенаправлением запросов только к нужным папкам:

- Прокси-сервер (Nginx) перенаправляет `/downloads/` на Flask (или FastAPI) сервер
- Все остальные пути блокируются
- Таким образом, клиент получает доступ **только к готовым файлам**, не к логике сервера


---

## 🤖 Как это работает

1. Пользователь отправляет боту ссылку на YouTube
2. Бот скачивает видео
3. Если видео < 50 МБ — отправляется прямо в Telegram
4. Иначе — формируется уникальная ссылка на скачивание

---

## 📌 Примечания

- Убедитесь, что директория `downloads/` имеет права на чтение NGINX (обычно `www-data`)
- Не забывайте обновлять токен, если он будет отозван
- Сохранение чатов и логика очистки — автоматизированы

