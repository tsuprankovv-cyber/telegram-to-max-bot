import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class MAXMediaUploader:
    """Класс для загрузки медиафайлов в MAX"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_upload_url(self, media_type: str) -> dict:
        """Получает URL для загрузки файла в MAX"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads?type={media_type}"
        headers = {"Authorization": self.token}
        
        async with self.session.post(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка получения URL: {resp.status} - {error_text}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> str:
        """Загружает файл в MAX и возвращает токен"""
        await self.ensure_session()
        
        form = aiohttp.FormData()
        form.add_field('data', file_data, filename=filename, 
                      content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream')
        
        async with self.session.post(upload_url, data=form) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get('token')
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка загрузки: {resp.status} - {error_text}")

class TelegramDownloader:
    """Класс для скачивания файлов из Telegram"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']['file_path']
            else:
                raise Exception(f"Ошибка получения пути файла: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл из Telegram и возвращает (данные, имя_файла)"""
        await self.ensure_session()
        
        file_path = await self.get_file_path(file_id)
        filename = file_path.split('/')[-1]
        
        url = f"{self.base_url}/{file_path}"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return (await resp.read(), filename)
            else:
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Создаем экземпляры классов
max_uploader = MAXMediaUploader(MAX_TOKEN)
tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max_channel(text: str, attachments: list = None):
    """Отправляет сообщение в канал MAX"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    message_data = {"text": text}
    if attachments:
        message_data["attachments"] = attachments
    
    data = {
        "recipient": {
            "chat_id": str(MAX_CHANNEL_ID)
        },
        "message": message_data
    }
    
    logger.info(f"📤 Отправка в MAX")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ Успешно отправлено")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Ошибка MAX: {resp.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

def get_media_type(message: types.Message) -> str:
    """Определяет тип медиа в сообщении"""
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.audio:
        return 'audio'
    elif message.voice:
        return 'voice'
    elif message.document:
        return 'document'
    elif message.animation:
        return 'animation'
    return None

async def process_media(message: types.Message) -> list:
    """Обрабатывает медиа из сообщения"""
    attachments = []
    media_type = get_media_type(message)
    
    if not media_type:
        return attachments
    
    try:
        file_id = None
        filename = None
        
        if message.photo:
            file_id = message.photo[-1].file_id
            filename = f"photo_{datetime.now().timestamp()}.jpg"
        elif message.video:
            file_id = message.video.file_id
            filename = message.video.file_name or f"video_{datetime.now().timestamp()}.mp4"
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or f"audio_{datetime.now().timestamp()}.mp3"
        elif message.voice:
            file_id = message.voice.file_id
            filename = f"voice_{datetime.now().timestamp()}.ogg"
        elif message.document:
            file_id = message.document.file_id
            filename = message.document.file_name
        elif message.animation:
            file_id = message.animation.file_id
            filename = message.animation.file_name or f"animation_{datetime.now().timestamp()}.gif"
        
        if not file_id:
            return attachments
        
        # Для фото - быстрая отправка по URL
        if media_type == 'photo':
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"🖼️ Фото обработано")
        
        # Для остальных типов - загрузка через токен
        else:
            file_data, original_filename = await tg_downloader.download_file(file_id)
            
            max_type = media_type
            if media_type == 'voice':
                max_type = 'audio'
            elif media_type == 'animation':
                max_type = 'video'
            
            upload_info = await max_uploader.get_upload_url(max_type)
            token = await max_uploader.upload_file(
                upload_info['url'], 
                file_data, 
                original_filename or filename
            )
            
            attachments.append({
                "type": max_type,
                "payload": {"token": token}
            })
            logger.info(f"📦 {media_type} обработано")
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
    
    return attachments

async def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            button_row = []
            for btn in row:
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                buttons.append(button_row)
        
        if buttons:
            logger.info(f"🔘 Найдено {len(buttons)} рядов кнопок")
    
    return buttons

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает ВСЕ сообщения из Telegram-группы в MAX-канал"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        logger.info(f"📨 Получено от {message.from_user.full_name or 'пользователь'} (бот: {message.from_user.is_bot})")
        
        # Текст сообщения (чистый, без префиксов)
        text = message.text or message.caption or ""
        
        # Обрабатываем медиа
        attachments = await process_media(message)
        
        # Извлекаем кнопки
        buttons = await extract_buttons(message)
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
        
        # Отправляем в MAX
        success = await send_to_max_channel(text, attachments)
        
        if success:
            logger.info("✅ Сообщение переслано")
        else:
            logger.error("❌ Не удалось переслать")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ Бот запущен!\n\n"
        "Пересылает:\n"
        "• Любые сообщения (включая ботов)\n"
        "• Фото, видео, аудио\n"
        "• Голосовые сообщения\n"
        "• Кнопки-ссылки\n"
        "• Эмодзи и форматирование"
    )

async def cleanup():
    await max_uploader.close()
    await tg_downloader.close()

async def main():
    logger.info("🚀 Бот запускается...")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    finally:
        asyncio.run(cleanup())
