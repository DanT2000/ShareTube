#!/bin/bash

set -e

APP_NAME="ShareTube"
APP_DIR="/opt/$APP_NAME"
PORT=5000
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
SCRIPT_SOURCE="main.py"

function install_sharetube() {
    echo "🔧 Проверка установки Python..."
    if ! command -v python3 &> /dev/null; then
        echo "🐍 Python не найден. Устанавливаем..."
        sudo apt update
        sudo apt install -y python3 python3-venv python3-pip
    else
        echo "✅ Python уже установлен."
    fi
    echo "🎞️ Устанавливаем ffmpeg..."
    sudo apt install -y ffmpeg
    echo "📂 Создаем директорию $APP_DIR..."
    sudo mkdir -p "$APP_DIR"
    sudo chown "$USER":"$USER" "$APP_DIR"

    echo "📄 Копируем скрипт $SCRIPT_SOURCE в $APP_DIR..."
    cp "$SCRIPT_SOURCE" "$APP_DIR/"

    cd "$APP_DIR"

    echo "🐍 Создаем виртуальное окружение..."
    python3 -m venv venv

    echo "🚀 Активируем виртуальное окружение и устанавливаем зависимости..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install pytelegrambotapi yt-dlp flask
    deactivate

    echo "🌐 Открываем порт $PORT через iptables..."
    sudo iptables -I INPUT -p tcp --dport $PORT -j ACCEPT
    sudo apt install -y iptables-persistent
    sudo netfilter-persistent save

    echo "🧾 Создаем systemd-сервис..."

    sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=ShareTube - Telegram YouTube Downloader
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/$SCRIPT_SOURCE
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    echo "📡 Перезапускаем systemd и включаем сервис..."
    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload
    sudo systemctl enable $APP_NAME
    sudo systemctl start $APP_NAME

    echo "✅ Установка завершена!"
    echo "⚠️ Не забудь отредактировать файл $APP_DIR/$SCRIPT_SOURCE и указать свой Telegram-токен и IP-адрес в самом начале."
    echo "📦 Приложение работает как служба: systemctl status $APP_NAME"
}

function uninstall_sharetube() {
    echo "🛑 Останавливаем и удаляем службу..."
    sudo systemctl stop $APP_NAME || true
    sudo systemctl disable $APP_NAME || true
    sudo rm -f "$SERVICE_FILE"
    sudo systemctl daemon-reload

    echo "🔥 Удаляем приложение из $APP_DIR..."
    sudo rm -rf "$APP_DIR"

    echo "🚫 Закрываем порт $PORT..."
    sudo iptables -D INPUT -p tcp --dport $PORT -j ACCEPT || true
    sudo netfilter-persistent save

    echo "🧹 ShareTube удалён с системы!"
}

clear
echo "=============================="
echo "       ShareTube Setup"
echo "=============================="
echo "1️⃣  Установить ShareTube"
echo "2️⃣  Удалить ShareTube"
echo "0️⃣  Выйти"
echo "------------------------------"
read -p "Введите номер действия: " ACTION

case "$ACTION" in
    1)
        install_sharetube
        ;;
    2)
        uninstall_sharetube
        ;;
    0)
        echo "👋 Выход."
        exit 0
        ;;
    *)
        echo "❌ Неверный выбор. Попробуйте снова."
        exit 1
        ;;
esac
