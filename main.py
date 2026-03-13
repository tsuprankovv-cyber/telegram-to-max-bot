import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional, Dict

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

logger.info("="*80)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === ХРАНИЛИЩЕ ДЛЯ АЛЬБОМОВ ===
albums: Dict[str, List[types.Message]] = {}
album_lock = asyncio.Lock()

# === ТРАНСЛИТЕРАЦИЯ ===
TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}

def transliterate(text: str) -> str:
    result = []
    for char in text:
        if char in TRANSLIT_DICT:
            result.append(TRANSLIT_DICT[char])
        else:
            result.append(char)
    return ''.join(result)

def safe_filename(filename: str) -> str:
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    
    name = transliterate(name)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    
    if not name:
        name = 'file'
    
    result = f"{name}.{ext}" if ext else name
    logger.debug(f"🏷️ Имя файла: '{filename}' -> '{result}'")
    return result

# === ТЕКСТОВЫЕ ФУНКЦИИ ===
def format_text(text: str, entities: list) -> str:
    """Простое форматирование текста с entities"""
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

class MediaUploader:
    """Загрузчик медиа"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        self.stats = {
            "documents_ok": 0, "documents_failed": 0,
            "video_ok": 0, "video_failed": 0,
            "audio_ok": 0, "audio_failed": 0,
            "voice_ok": 0, "voice_failed": 0,
            "photo_ok": 0,
            "albums_ok": 0
        }
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def create_upload(self, media_type: str) -> dict:
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 [ЗАГРУЗКА] Создание загрузки для {media_type}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ФАЙЛ] Загрузка: {filename}")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            return resp.status == 200
    
    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ФАЙЛ] Загрузка: {filename}")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            if resp.status == 200:
                try:
                    result = await resp.json()
                    return result.get('token')
                except:
                    return None
            return None
    
    async def upload_video(self, file_data: bytes, filename: str, file_size: int = None) -> Optional[str]:
        """Загрузка видео с динамической паузой в зависимости от размера"""
        try:
            safe_name = safe_filename(filename)
            
            # Определяем размер видео
            if file_size:
                file_size_mb = file_size / (1024 * 1024)
            else:
                file_size_mb = len(file_data) / (1024 * 1024)
            
            logger.info(f"🎥 [ВИДЕО] Загрузка: {filename} ({file_size_mb:.1f} MB)")
            
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["video_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                # Динамическая пауза: минимум 3 сек, дальше по формуле
                wait_time = max(3, file_size_mb / 2)
                logger.info(f"⏳ [ВИДЕО] Ожидание обработки ({wait_time:.1f} сек)...")
                await asyncio.sleep(wait_time)
                
                self.stats["video_ok"] += 1
                logger.info(f"✅ [ВИДЕО] {safe_name} готов")
                return token
            else:
                self.stats["video_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка видео: {e}")
            self.stats["video_failed"] += 1
            return None
    
    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"📄 [ДОКУМЕНТ] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["documents_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            
            if token:
                self.stats["documents_ok"] += 1
                return (token, safe_name)
            else:
                self.stats["documents_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка документа: {e}")
            self.stats["documents_failed"] += 1
            return None
    
    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎵 [АУДИО] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["audio_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            
            if token:
                self.stats["audio_ok"] += 1
                return (token, safe_name)
            else:
                self.stats["audio_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка аудио: {e}")
            self.stats["audio_failed"] += 1
            return None
    
    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            file_size_mb = len(file_data) / (1024 * 1024)
            
            logger.info(f"🎤 [ГОЛОСОВОЕ] Загрузка: {filename} ({file_size_mb:.1f} MB)")
            
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                # Для голосовых чуть меньше времени
                wait_time = max(2, file_size_mb / 3)
                logger.info(f"⏳ [ГОЛОСОВОЕ] Ожидание обработки ({wait_time:.1f} сек)...")
                await asyncio.sleep(wait_time)
                
                self.stats["voice_ok"] += 1
                return token
            else:
                self.stats["voice_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка голосового: {e}")
            self.stats["voice_failed"] += 1
            return None

class TelegramDownloader:
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_info(self, file_id: str) -> dict:
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            else:
                raise Exception(f"Ошибка получения информации: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
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

# Инициализируем
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max(text: str, attachments: List[dict] = None):
    if not attachments:
        logger.warning("⚠️ Нет вложений")
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
    
    logger.info("="*80)
    logger.info(f"📤 ОТПРАВКА В MAX")
    logger.info(f"📎 Вложений: {len(attachments)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    response_text = await resp.text()
                    logger.error(f"❌ Ошибка {resp.status}: {response_text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

async def process_single_media(message: types.Message) -> Tuple[str, List[dict]]:
    """Обработка одного медиа-сообщения"""
    attachments = []
    text = message.caption or ""
    
    try:
        # ФОТО
        if message.photo:
            logger.info("🖼️ [ФОТО] Обработка")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1
        
        # ВИДЕО
        elif message.video:
            logger.info("🎥 [ВИДЕО] Обработка")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename, message.video.file_size)
            if token:
                attachments.append({
                    "type": "video",
                    "payload": {"token": token}
                })
        
        # АУДИО
        elif message.audio:
            logger.info("🎵 [АУДИО] Обработка")
            file_data, _ = await downloader.download_file(message.audio.file_id)
            original_name = message.audio.file_name or "audio.mp3"
            result = await uploader.upload_audio(file_data, original_name)
            if result:
                token, safe_name = result
                attachments.append({
                    "type": "file",
                    "payload": {"token": token, "name": safe_name}
                })
        
        # ГОЛОСОВЫЕ
        elif message.voice:
            logger.info("🎤 [ГОЛОСОВОЕ] Обработка")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({
                    "type": "audio",
                    "payload": {"token": token}
                })
        
        # ДОКУМЕНТЫ
        elif message.document:
            file_name = message.document.file_name
            logger.info(f"📄 [ДОКУМЕНТ] Обработка: {file_name}")
            
            file_data, _ = await downloader.download_file(message.document.file_id)
            
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt']:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
            
            elif ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
                token = await uploader.upload_video(file_data, file_name, message.document.file_size)
                if token:
                    attachments.append({
                        "type": "video",
                        "payload": {"token": token}
                    })
            
            elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac']:
                result = await uploader.upload_audio(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
            
            else:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    
    return text, attachments

async def process_album_messages(messages: List[types.Message]) -> Tuple[str, List[dict]]:
    """Обработка всех сообщений из альбома"""
    all_attachments = []
    caption = messages[0].caption or ""
    
    logger.info(f"📸 [АЛЬБОМ] Обработка {len(messages)} сообщений")
    
    # Сортируем сообщения: сначала фото, потом видео
    sorted_messages = sorted(messages, key=lambda m: (
        0 if m.photo else 1,
        m.message_id
    ))
    
    for i, msg in enumerate(sorted_messages):
        logger.info(f"📸 [АЛЬБОМ] Элемент {i+1}: {'фото' if msg.photo else 'видео'}")
        _, attachments = await process_single_media(msg)
        all_attachments.extend(attachments)
        
        # Если это видео, даём динамическую паузу в зависимости от размера
        if msg.video and msg.video.file_size:
            file_size_mb = msg.video.file_size / (1024 * 1024)
            wait_time = max(1, file_size_mb / 5)
            logger.info(f"⏳ [АЛЬБОМ] Пауза для видео ({wait_time:.1f} сек)")
            await asyncio.sleep(wait_time)
    
    uploader.stats["albums_ok"] += 1
    logger.info(f"📸 [АЛЬБОМ] Всего вложений: {len(all_attachments)}")
    return caption, all_attachments

async def album_processor(album_id: str, messages: List[types.Message], delay: int = 3):
    """Обрабатывает альбом после задержки"""
    await asyncio.sleep(delay)
    
    async with album_lock:
        if album_id in albums:
            logger.info(f"📸 [АЛЬБОМ] Обработка альбома {album_id}")
            caption, attachments = await process_album_messages(messages)
            if attachments:
                # Форматируем подпись
                if messages[0].caption_entities:
                    caption = format_text(caption, messages[0].caption_entities)
                
                # Добавляем подпись о пересылке
                if messages[0].forward_date and messages[0].forward_from_chat:
                    source = messages[0].forward_from_chat.title
                    caption = f"📢 Переслано из {source}:\n\n{caption}"
                
                await send_to_max(caption, attachments)
            else:
                logger.warning(f"⚠️ [АЛЬБОМ] Нет вложений для отправки")
            
            # Очищаем альбом
            del albums[album_id]

@dp.message()
async def forward(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    # Проверяем, является ли сообщение частью альбома
    if message.media_group_id:
        album_id = message.media_group_id
        logger.info(f"📸 [АЛЬБОМ] Получена часть {album_id}")
        
        async with album_lock:
            # Добавляем сообщение в альбом
            if album_id not in albums:
                albums[album_id] = []
                # Запускаем обработчик альбома
                asyncio.create_task(album_processor(album_id, albums[album_id]))
            
            albums[album_id].append(message)
            logger.info(f"📸 [АЛЬБОМ] В альбоме {len(albums[album_id])} сообщений")
        
        return
    
    # Обработка одиночных медиа
    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Обработка одиночного медиа")
        text, attachments = await process_single_media(message)
        
        if not attachments:
            logger.warning("⚠️ Нет вложений")
            return
        
        # Форматируем подпись
        if message.caption:
            text_entities = message.caption_entities
            if text and text_entities:
                text = format_text(text, text_entities)
        
        if message.forward_date and message.forward_from_chat:
            source = message.forward_from_chat.title
            text = f"📢 Переслано из {source}:\n\n{text}"
        
        await send_to_max(text, attachments)
        return
    
    # ТЕКСТ
    if message.text:
        logger.info("📝 Обработка текста")
        text = message.text or ""
        entities = message.entities or []
        
        formatted_text = format_text(text, entities)
        
        if message.forward_date and message.forward_from_chat:
            formatted_text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{formatted_text}"
        
        await send_to_max(formatted_text)
        return

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК MAX**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 📝 Текст (форматирование)\n"
        "• 📄 PDF, DOC, XLS (транслит)\n"
        "• 🎥 Видео (с динамической паузой)\n"
        "• 🎵 Аудио (с именами)\n"
        "• 🎤 Голосовые\n"
        "• 🖼️ Фото\n"
        "• 📸 Альбомы (фото+фото, видео+видео, фото+видео)\n"
        "• 📦 Пакетная отправка\n\n"
        "📊 Статистика: /stats"
    )

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    await message.answer(
        f"📊 **СТАТИСТИКА:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']}\n"
        f"📸 Альбомы: ✅ {stats['albums_ok']}"
    )

async def cleanup():
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()

async def main():
    logger.info("🚀 ЗАПУСК БОТА (С ДИНАМИЧЕСКОЙ ПАУЗОЙ ДЛЯ ВИДЕО)")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
