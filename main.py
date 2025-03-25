import os
import threading
import telebot
import yt_dlp
from flask import Flask, send_from_directory
from urllib.parse import quote
import json
# Параметры бота
BOT_TOKEN = "YOU_TOKEN***************"

# Параметры сервера
SERVER_IP = "YOU IP***************"  # или укажите внешний IP, если сервер доступен извне
SERVER_LOCAL_IP = "127.0.0.1"
SERVER_PORT = 5000
# Максимальный размер папки в байтах (3 ГБ)
MAX_FOLDER_SIZE = int(3 * 1024 * 1024 * 1024)
# Директория для загрузки файлов
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация Flask-сервера
app = Flask(__name__)

@app.route('/downloads/<path:filename>')
def download_file(filename):
    """Обработчик для раздачи файлов из папки downloads."""
    return send_from_directory(DOWNLOAD_DIR, filename)

def run_flask():
    """Функция для запуска Flask-сервера."""
    app.run(host=SERVER_LOCAL_IP, port=SERVER_PORT)
    
@app.route("/")
def home():
    return "Flask работает через Nginx!"


@bot.message_handler(commands=["start"])
def send_welcome(message):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Привет! Я бот для скачивания видео с YouTube.\n\n"
        "🔹 Отправь мне ссылку на видео, и я загружу его.\n"
        "🔹 Если видео короче 1 минуты, я отправлю его прямо сюда.\n"
        "🔹 Если видео длиннее, пришлю ссылку для скачивания.\n\n"
        "⚠️ Учти, что Telegram ограничивает размер файлов до 50 МБ, "
        "поэтому для длинных видео лучше использовать ссылку."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=["restart"])
def restart_bot(message):
    """Обработчик команды /restart"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Укажите здесь ваш Telegram ID, чтобы команда работала только для вас
    ALLOWED_USER_ID = 868209405  # Замените на ваш ID

    if user_id == ALLOWED_USER_ID:
        bot.send_message(chat_id, "🔄 Перезапускаю бота...")
        os.system("sudo systemctl restart sharetube_bot.service")
    else:
        bot.send_message(chat_id, "⛔ У вас нет прав для выполнения этой команды.")

        



def get_folder_size(folder):
    """Возвращает общий размер файлов в указанной папке."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)

    return total_size

def free_up_space(required_space,filename):
    """Освобождает место в папке downloads, удаляя файлы, кроме последнего загруженного."""
    files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
    files.sort(key=os.path.getctime)  # Сортируем файлы по дате создания (от старых к новым)

    current_size = get_folder_size(DOWNLOAD_DIR)
    print(files)
    if required_space > MAX_FOLDER_SIZE:
        # Если файл больше максимального размера папки, удаляем все файлы
        for file in files:
            if os.path.basename(file) == filename:
                continue
            try:
                os.remove(file)
                print(f"Удален файл: {file}")
            except Exception as e:
                print(f"Ошибка при удалении файла {file}: {e}")
    else:
        # Удаляем файлы, пока размер папки не станет меньше допустимого
        while files and current_size > MAX_FOLDER_SIZE:
            file_to_delete = files.pop(0)
            try:
                file_size = os.path.getsize(file_to_delete)
                os.remove(file_to_delete)
                current_size -= file_size
                print(f"Удален файл: {file_to_delete}")
            except Exception as e:
                print(f"Ошибка при удалении файла {file_to_delete}: {e}")













@bot.message_handler(func=lambda message: message.text and ("youtube.com" in message.text or "youtu.be" in message.text))
def handle_youtube_link(message):
    """Обработчик сообщений с ссылками на YouTube"""
    url = message.text.strip()
    chat_id = message.chat.id
    if message.chat.type == 'private':
        bot.send_message(chat_id, "🔍 Проверяю видео...")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, 'temp.%(ext)s'),
    }
    # Путь к файлу cookies в той же директории, что и index.py
    cookie_path = os.path.join(os.path.dirname(__file__), 'www.youtube.com_cookies.txt')
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info_dict = ydl.extract_info(url, download=False)
            video_duration = info_dict.get('duration', 0)
            video_ext = info_dict.get('ext', 'mp4')
            # Определяем новое имя файла
            existing_files = os.listdir(DOWNLOAD_DIR)
            video_index = len(existing_files) + 1
            new_filename = f"video_{video_index}.{video_ext}"
            new_filepath = os.path.join(DOWNLOAD_DIR, new_filename)
            ydl.download([url])
            video_size = os.path.getsize(os.path.join(DOWNLOAD_DIR, f"temp.{video_ext}"))
            if video_size < 50 * 1024 * 1024:
                if message.chat.type == 'private':
                    bot.send_message(chat_id, "⏳ Короткое видео, загружаю и отправляю...")
                temp_filepath = os.path.join(DOWNLOAD_DIR, f"temp.{video_ext}")
                os.rename(temp_filepath, new_filepath)
                with open(new_filepath, 'rb') as video_file:
                    bot.send_video(chat_id, video_file, caption=f"Оригинал: {url}")
                os.remove(new_filepath)
                bot.delete_message(chat_id, message.message_id)
            else:
                if message.chat.type == 'private':
                    bot.send_message(chat_id, "⏳ Длинное видео, загружаю и предоставлю ссылку...")
                ydl.download([url])
                temp_filepath = os.path.join(DOWNLOAD_DIR, f"temp.{video_ext}")
                while os.path.exists(new_filepath):
                    video_index += 1
                    new_filename = f"video_{video_index}.{video_ext}"
                    new_filepath = os.path.join(DOWNLOAD_DIR, new_filename)
                os.rename(temp_filepath, new_filepath)
                encoded_filename = quote(new_filename)
                download_link = f"http://{SERVER_IP}:{SERVER_PORT}/downloads/{encoded_filename}"
                bot.send_message(chat_id, f"📥 Видео загружено. Скачай его по ссылке: {download_link}")
                # Проверяем, нужно ли освободить место
                video_size = os.path.getsize(new_filepath)
                
                current_folder_size = get_folder_size(DOWNLOAD_DIR)


                if current_folder_size + video_size > MAX_FOLDER_SIZE:
                    free_up_space(video_size,encoded_filename)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка при обработке видео: {str(e)}")
    # Удаляем сообщение пользователя после обработки
    
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=30)
    except requests.exceptions.ConnectionError:
        print("❌ Потеряно соединение с Telegram API. Перезапускаю polling через 5 секунд...")
        time.sleep(5)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        time.sleep(5)
