import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional

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
    """Загрузчик для всех типов медиа согласно документации MAX API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        self.stats = {"documents": 0, "video": 0, "audio": 0, "image": 0, "failed": 0}
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def create_upload(self, media_type: str) -> dict:
        """
        ШАГ 1: Создаём загрузку
        media_type: 'video' | 'audio' | 'file' | 'image'
        """
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 [ШАГ 1] Создание загрузки для {media_type}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                result = await resp.json()
                logger.info(f"✅ [ШАГ 1] Получен upload_url и токен")
                return result
            else:
                error = await resp.text()
                logger.error(f"❌ [ШАГ 1] Ошибка {resp.status}: {error}")
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        """
        ШАГ 2: Загружаем файл по полученному URL
        """
        await self.ensure_session()
        
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ШАГ 2] Загрузка: {filename} ({content_type})")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            if resp.status == 200:
                logger.info(f"✅ [ШАГ 2] Файл загружен")
                return True
            else:
                error = await resp.text()
                logger.error(f"❌ [ШАГ 2] Ошибка {resp.status}: {error}")
                return False
    
    async def upload_document(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загружает документ и возвращает токен"""
        try:
            upload_info = await self.create_upload("file")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if await self.upload_file(upload_url, file_data, filename):
                self.stats["documents"] += 1
                return token
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки документа: {e}")
            self.stats["failed"] += 1
            return None
    
    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загружает видео и возвращает токен"""
        try:
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if await self.upload_file(upload_url, file_data, filename):
                self.stats["video"] += 1
                # Для видео тоже нужна пауза [citation:3]
                await asyncio.sleep(2)
                return token
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки видео: {e}")
            self.stats["failed"] += 1
            return None
    
    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загружает аудио и возвращает токен"""
        try:
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if await self.upload_file(upload_url, file_data, filename):
                self.stats["audio"] += 1
                # Для аудио нужна пауза [citation:3]
                await asyncio.sleep(2)
                return token
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки аудио: {e}")
            self.stats["failed"] += 1
            return None

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
                error = await resp.text()
                raise Exception(f"Ошибка получения информации: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл и возвращает (данные, имя_файла)"""
        await self.ensure_session()
        
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        
        # Пытаемся получить оригинальное имя из Telegram
        if hasattr(file_info, 'file_name') and file_info['file_name']:
            filename = file_info['file_name']
        
        url = f"{self.file_url}/{file_path}"
        logger.info(f"📥 Скачивание: {filename}")
        
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                logger.info(f"✅ Скачано {len(data)} байт")
                return (data, filename)
            else:
                error = await resp.text()
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Инициализируем
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

async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
    """
    УНИВЕРСАЛЬНЫЙ обработчик для ВСЕХ типов с поддержкой пакетной отправки
    """
    attachments = []
    text = message.caption or ""
    
    try:
        # ФОТО - всегда прямая ссылка (работает без токена) [citation:1]
        if message.photo:
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info("🖼️ Фото (прямая ссылка)")
        
        # ВИДЕО
        elif message.video:
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({
                    "type": "video",
                    "payload": {"token": token}
                })
                logger.info(f"🎥 Видео загружено: {filename}")
        
        # АУДИО
        elif message.audio:
            file_data, filename = await downloader.download_file(message.audio.file_id)
            token = await uploader.upload_audio(file_data, filename)
            if token:
                attachments.append({
                    "type": "audio",
                    "payload": {"token": token}
                })
                logger.info(f"🎵 Аудио загружено: {filename}")
        
        # ГОЛОСОВЫЕ (обрабатываются как аудио)
        elif message.voice:
            file_data, filename = await downloader.download_file(message.voice.file_id)
            # Переименовываем для единообразия
            filename = filename.rsplit('.', 1)[0] + '.mp3'
            token = await uploader.upload_audio(file_data, filename)
            if token:
                attachments.append({
                    "type": "audio",
                    "payload": {"token": token}
                })
                logger.info(f"🎤 Голосовое загружено")
        
        # ДОКУМЕНТЫ - ВАЖНО! [citation:3]
        elif message.document:
            file_name = message.document.file_name
            file_data, _ = await downloader.download_file(message.document.file_id)
            
            # Определяем тип документа по расширению
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            # Документы (PDF, DOC, DOCX, XLS, XLSX, TXT и др.)
            document_formats = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'rtf', 'odt', 'ods']
            image_formats = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']
            video_formats = ['mp4', 'mov', 'avi', 'mkv', 'webm']
            audio_formats = ['mp3', 'wav', 'ogg', 'm4a', 'flac']
            
            if ext in document_formats:
                logger.info(f"📄 Документ: {file_name}")
                token = await uploader.upload_document(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": file_name}
                    })
                    logger.info(f"✅ {file_name} загружен")
            
            elif ext in image_formats:
                logger.info(f"🖼️ Изображение как документ: {file_name}")
                # Для изображений лучше использовать прямую ссылку
                file_url = await downloader.get_file_info(message.document.file_id)
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_url['file_path']}"
                attachments.append({
                    "type": "image",
                    "payload": {"url": file_url}
                })
            
            elif ext in video_formats:
                logger.info(f"🎥 Видео как документ: {file_name}")
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "video",
                        "payload": {"token": token}
                    })
            
            elif ext in audio_formats:
                logger.info(f"🎵 Аудио как документ: {file_name}")
                token = await uploader.upload_audio(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "audio",
                        "payload": {"token": token}
                    })
            
            else:
                # Неизвестный тип - как file
                logger.info(f"📄 Файл: {file_name}")
                token = await uploader.upload_document(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": file_name}
                    })
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        uploader.stats["failed"] += 1
    
    return text, attachments

async def send_to_max(text: str, attachments: List[dict] = None):
    """Отправляет сообщение в MAX с поддержкой множественных вложений [citation:4]"""
    if not attachments:
        logger.warning("⚠️ Нет вложений для отправки")
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
    for i, att in enumerate(attachments, 1):
        att_type = att['type']
        payload = att['payload']
        if 'name' in payload:
            logger.info(f"   {i}. {att_type}: {payload['name']}")
        elif 'url' in payload:
            logger.info(f"   {i}. {att_type}: URL")
        elif 'token' in payload:
            logger.info(f"   {i}. {att_type}: токен {payload['token'][:20]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Ошибка {resp.status}: {error}")
                    
                    # Специальная обработка attachment.not.ready [citation:3]
                    if 'attachment.not.ready' in error:
                        logger.info("⏳ Файл ещё обрабатывается, нужно подождать")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward(message: types.Message):
    """Основной обработчик"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*70)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    text, attachments = await process_media_message(message)
    
    if not attachments:
        logger.warning("⚠️ Нет вложений для отправки")
        return
    
    # Обрабатываем текст
    if message.caption:
        text_entities = message.caption_entities
    else:
        text_entities = message.entities
    
    if text and text_entities:
        text = process_text_part(text, text_entities)
    
    # Добавляем подпись для пересланных
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        text = f"📢 Переслано из {source}:\n\n{text}"
    
    # Отправляем
    await send_to_max(text, attachments)

@dp.message(Command("start"))
async def start(message: types.Message):
    stats = uploader.stats
    await message.answer(
        "✅ **УНИВЕРСАЛЬНЫЙ БОТ MAX**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 🖼️ Фото (прямые ссылки)\n"
        "• 🎥 Видео (токены)\n"
        "• 🎵 Аудио (токены)\n"
        "• 🎤 Голосовые (токены)\n"
        "• 📄 PDF, DOC, DOCX, XLS, XLSX, TXT\n"
        "• 📦 Пакетная отправка нескольких файлов\n"
        "• 💾 Сохранение оригинальных имён\n\n"
        f"📊 **Статистика:**\n"
        f"• Документы: {stats['documents']}\n"
        f"• Видео: {stats['video']}\n"
        f"• Аудио: {stats['audio']}\n"
        f"• Фото: {stats['image']}\n"
        f"• Ошибки: {stats['failed']}\n\n"
        "Отправляйте файлы в группу!"
    )

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    await message.answer(
        f"📊 **СТАТИСТИКА ЗАГРУЗОК:**\n\n"
        f"• Документы: {stats['documents']}\n"
        f"• Видео: {stats['video']}\n"
        f"• Аудио: {stats['audio']}\n"
        f"• Фото: {stats['image']}\n"
        f"• Ошибки: {stats['failed']}"
    )

async def cleanup():
    """Закрытие сессий"""
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()
    logger.info(f"📊 Итоговая статистика: {uploader.stats}")

async def main():
    logger.info("🚀 ЗАПУСК УНИВЕРСАЛЬНОГО БОТА MAX")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
