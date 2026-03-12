import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class MediaUploader:
    """Загрузчик для всех типов медиа"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def create_upload(self, media_type: str) -> dict:
        """ШАГ 1: Создаём загрузку"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 [ШАГ 1] Создание загрузки для {media_type}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result
            else:
                error = await resp.text()
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        """ШАГ 2: Загружаем файл"""
        await self.ensure_session()
        
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ШАГ 2] Загрузка: {filename}")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            if resp.status == 200:
                return True
            else:
                return False

class TelegramDownloader:
    """Класс для скачивания файлов из Telegram"""
    
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_info(self, file_id: str) -> dict:
        """Получает информацию о файле"""
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            else:
                raise Exception(f"Ошибка получения информации: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл"""
        await self.ensure_session()
        
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        
        url = f"{self.file_url}/{file_path}"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return (data, filename)
            else:
                raise Exception(f"Ошибка скачивания: {resp.status}")

uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

def format_text_with_entities(text: str, entities: list) -> str:
    """Форматирует текст с entities"""
    if not entities or not text:
        return text or ""
    
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        fragment = result[start:end]
        
        if entity.type == "bold":
            replacement = f"**{fragment}**"
        elif entity.type == "italic":
            replacement = f"*{fragment}*"
        elif entity.type == "underline":
            replacement = f"++{fragment}++"
        elif entity.type == "strikethrough":
            replacement = f"~~{fragment}~~"
        elif entity.type == "text_link":
            replacement = f"[{fragment}]({entity.url})"
        elif entity.type == "blockquote":
            replacement = f"> {fragment}"
        else:
            continue
        
        result = result[:start] + replacement + result[end:]
    
    return result

def is_heading(text: str, entities: list) -> bool:
    """Проверяет заголовок"""
    if not entities or not text:
        return False
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    if first.offset != 0 or first.type != "bold":
        return False
    
    last_pos = 0
    last_bold_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        last_bold_end = e.offset + e.length
        last_pos = last_bold_end
    
    if last_bold_end == 0:
        return False
    
    text_after = text[last_bold_end:].lstrip()
    return bool(text_after)

def extract_heading_text(text: str, entities: list) -> tuple[str, str, list]:
    """Извлекает заголовок"""
    if not entities:
        return "", text, []
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    last_pos = 0
    heading_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
    
    if heading_end == 0:
        return "", text, entities
    
    heading = text[:heading_end]
    after_raw = text[heading_end:]
    after_stripped = after_raw.lstrip()
    spaces = len(after_raw) - len(after_stripped)
    
    remaining_entities = []
    shift = heading_end + spaces
    
    for e in sorted_entities:
        if e.offset >= heading_end:
            new_e = type('Entity', (), {})()
            new_e.offset = e.offset - shift
            new_e.length = e.length
            new_e.type = e.type
            if hasattr(e, 'url'):
                new_e.url = e.url
            remaining_entities.append(new_e)
    
    return heading, after_stripped, remaining_entities

def process_text_part(text: str, entities: list) -> str:
    """Обрабатывает текст"""
    if not text:
        return ""
    
    if is_heading(text, entities):
        heading, rest, rest_entities = extract_heading_text(text, entities)
        heading_formatted = f"# {heading}"
        
        if rest:
            rest_formatted = format_text_with_entities(rest, rest_entities)
            return f"{heading_formatted}\n\n{rest_formatted}"
        return heading_formatted
    
    return format_text_with_entities(text, entities)

async def upload_and_send(file_data: bytes, filename: str, media_type: str, text: str = "") -> dict:
    """Универсальная функция загрузки и отправки"""
    
    # ШАГ 1: Получаем upload_url и токен
    upload_info = await uploader.create_upload(media_type)
    file_token = upload_info.get('token')
    upload_url = upload_info.get('url')
    
    # ШАГ 2: Загружаем файл
    if not await uploader.upload_file(upload_url, file_data, filename):
        raise Exception("Ошибка загрузки файла")
    
    # Для аудио нужно подождать обработки
    if media_type == "audio":
        logger.info("⏳ Ожидание обработки аудио...")
        await asyncio.sleep(2)  # Ждём 2 секунды
    
    # Формируем attachment
    if media_type == "file":
        return {
            "type": "file",
            "payload": {"token": file_token, "name": filename}
        }
    else:
        return {
            "type": media_type,
            "payload": {"token": file_token}
        }

async def process_media_message(message: types.Message) -> tuple[str, list]:
    """Обрабатывает сообщение"""
    attachments = []
    text = message.caption or ""
    
    try:
        # ФОТО
        if message.photo:
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info("🖼️ Фото")
        
        # ВИДЕО
        elif message.video:
            file_data, filename = await downloader.download_file(message.video.file_id)
            att = await upload_and_send(file_data, filename, "video", text)
            attachments.append(att)
            logger.info(f"🎥 Видео: {filename}")
        
        # АУДИО
        elif message.audio:
            file_data, filename = await downloader.download_file(message.audio.file_id)
            att = await upload_and_send(file_data, filename, "audio", text)
            attachments.append(att)
            logger.info(f"🎵 Аудио: {filename}")
        
        # ГОЛОСОВЫЕ
        elif message.voice:
            file_data, filename = await downloader.download_file(message.voice.file_id)
            # Переименовываем в .mp3
            filename = filename.rsplit('.', 1)[0] + '.mp3'
            att = await upload_and_send(file_data, filename, "audio", text)
            attachments.append(att)
            logger.info(f"🎤 Голосовое")
        
        # ДОКУМЕНТЫ
        elif message.document:
            file_name = message.document.file_name
            file_data, _ = await downloader.download_file(message.document.file_id)
            
            # Определяем тип
            if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                media_type = "image"
                att = await upload_and_send(file_data, file_name, media_type, text)
            elif file_name.endswith(('.mp4', '.mov', '.avi')):
                media_type = "video"
                att = await upload_and_send(file_data, file_name, media_type, text)
            elif file_name.endswith(('.mp3', '.wav', '.ogg')):
                media_type = "audio"
                att = await upload_and_send(file_data, file_name, media_type, text)
            else:
                media_type = "file"
                att = await upload_and_send(file_data, file_name, media_type, text)
            
            attachments.append(att)
            logger.info(f"📄 {file_name}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    
    return text, attachments

async def send_to_max(text: str, attachments: list = None):
    """Отправляет в MAX"""
    if not attachments:
        return False
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text or " ",
        "format": "markdown",
        "attachments": attachments
    }
    
    logger.info("="*70)
    logger.info(f"📤 ОТПРАВКА: {len(attachments)} вложений")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Ошибка {resp.status}: {error}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*70)
    logger.info(f"📨 ID: {message.message_id}")
    
    text, attachments = await process_media_message(message)
    
    if not attachments:
        logger.warning("⚠️ Нет вложений")
        return
    
    if message.caption:
        text_entities = message.caption_entities
    else:
        text_entities = message.entities
    
    if text and text_entities:
        text = process_text_part(text, text_entities)
    
    if message.forward_date and message.forward_from_chat:
        text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
    
    await send_to_max(text, attachments)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **УНИВЕРСАЛЬНЫЙ БОТ**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 🖼️ Фото\n"
        "• 🎥 Видео\n"
        "• 🎵 Аудио\n"
        "• 🎤 Голосовые\n"
        "• 📄 PDF, DOC, XLS, TXT\n\n"
        "✅ **ВСЁ РАБОТАЕТ!**"
    )

async def main():
    logger.info("🚀 ЗАПУСК УНИВЕРСАЛЬНОГО БОТА")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
