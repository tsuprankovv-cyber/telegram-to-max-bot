import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
import math
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

# === ХРАНИЛИЩЕ ДЛЯ СООТВЕТСТВИЯ СООБЩЕНИЙ (для редактирования) ===
message_map: Dict[int, str] = {}

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
    return result

def split_file_into_chunks(file_path, chunk_size_mb=45):
    """
    Разбивает файл на части по chunk_size_mb мегабайт
    Возвращает список имён созданных файлов
    """
    chunk_size = chunk_size_mb * 1024 * 1024  # в байтах
    file_size = os.path.getsize(file_path)
    num_chunks = math.ceil(file_size / chunk_size)
    
    chunks = []
    with open(file_path, 'rb') as f:
        for i in range(num_chunks):
            chunk_filename = f"{file_path}.part{i+1:03d}"
            with open(chunk_filename, 'wb') as chunk_file:
                chunk_file.write(f.read(chunk_size))
            chunks.append(chunk_filename)
            logger.info(f"📦 Создана часть {i+1}/{num_chunks}")
    
    return chunks

# === ТЕКСТОВЫЕ ФУНКЦИИ ===
def format_text_with_entities(text: str, entities: list) -> str:
    """Применяет форматирование к тексту"""
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
        elif entity.type == "code":
            replacement = f"`{fragment}`"
        elif entity.type == "pre":
            replacement = f"```\n{fragment}\n```"
        elif entity.type == "text_link":
            replacement = f"[{fragment}]({entity.url})"
        elif entity.type == "blockquote":
            replacement = f"> {fragment}"
        else:
            continue
        
        result = result[:start] + replacement + result[end:]
    
    return result

def extract_buttons(message: types.Message) -> Optional[List[List[dict]]]:
    """Извлекает кнопки-ссылки из сообщения"""
    if not message.reply_markup or not message.reply_markup.inline_keyboard:
        return None
    
    buttons = []
    for row in message.reply_markup.inline_keyboard:
        button_row = []
        for button in row:
            if button.url:
                button_row.append({
                    "type": "link",
                    "text": button.text,
                    "url": button.url
                })
        if button_row:
            buttons.append(button_row)
    
    return buttons if buttons else None

# === КЛАСС ДЛЯ ЗАГРУЗКИ МЕДИА ===
class MediaUploader:
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
        """Создание загрузки - получаем URL и токен"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 [ЗАГРУЗКА] Создание загрузки для {media_type}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error = await resp.text()
                logger.error(f"❌ [ЗАГРУЗКА] Ошибка {resp.status}")
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        """Загружает файл на сервер MAX"""
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ФАЙЛ] Загрузка: {filename}")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            if resp.status == 200:
                logger.info(f"✅ [ФАЙЛ] {filename} загружен")
                return True
            else:
                logger.error(f"❌ [ФАЙЛ] Ошибка {resp.status}")
                return False
    
    async def upload_video(self, file_data: bytes, filename: str, file_size: int = None) -> Optional[str]:
        """Загрузка видео"""
        try:
            safe_name = safe_filename(filename)
            file_size_mb = len(file_data) / (1024 * 1024)
            logger.info(f"🎥 [ВИДЕО] Загрузка: {filename} ({file_size_mb:.1f} MB)")
            
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["video_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                wait_time = max(3, file_size_mb / 2)
                logger.info(f"⏳ [ВИДЕО] Ожидание обработки ({wait_time:.1f} сек)...")
                await asyncio.sleep(wait_time)
                
                self.stats["video_ok"] += 1
                return token
            else:
                self.stats["video_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка видео: {e}")
            self.stats["video_failed"] += 1
            return None
    
    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        """Загрузка аудио"""
        try:
            safe_name = safe_filename(filename)
            file_size_mb = len(file_data) / (1024 * 1024)
            logger.info(f"🎵 [АУДИО] Загрузка: {filename} ({file_size_mb:.1f} MB)")
            
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
    
    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        """Загрузка документа"""
        try:
            safe_name = safe_filename(filename)
            logger.info(f"📄 [ДОКУМЕНТ] Загрузка: {filename}")
            
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
    
    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка голосового"""
        try:
            safe_name = safe_filename(filename)
            file_size_mb = len(file_data) / (1024 * 1024)
            logger.info(f"🎤 [ГОЛОСОВОЕ] Загрузка ({file_size_mb:.1f} MB)")
            
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                wait_time = max(2, file_size_mb / 3)
                logger.info(f"⏳ [ГОЛОСОВОЕ] Ожидание ({wait_time:.1f} сек)...")
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
    
    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        """Загружает файл и возвращает токен из ответа"""
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
        """Скачивает файл из Telegram"""
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
                error = await resp.text()
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Инициализируем
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def create_attachment(message: types.Message) -> Optional[dict]:
    """
    Универсальная функция:
    - Фото → ссылка
    - Всё остальное → токен
    """
    try:
        # ФОТО - всегда через ссылку
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = await downloader.get_file_info(file_id)
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            logger.info("🖼️ [МЕДИА] Фото (ссылка)")
            return {
                "type": "image",
                "payload": {"url": file_url}
            }
        
        # ВИДЕО - через токен
        elif message.video:
            file_data, filename = await downloader.download_file(message.video.file_id)
            file_size_mb = len(file_data) / (1024 * 1024)
            logger.info(f"🎥 [МЕДИА] Видео ({file_size_mb:.1f} МБ) - загружаем токен")
            
            token = await uploader.upload_video(file_data, filename, message.video.file_size)
            if token:
                return {
                    "type": "video",
                    "payload": {"token": token}
                }
        
        # АУДИО - через токен
        elif message.audio:
            file_data, _ = await downloader.download_file(message.audio.file_id)
            logger.info(f"🎵 [МЕДИА] Аудио: {message.audio.file_name} - загружаем токен")
            
            result = await uploader.upload_audio(file_data, message.audio.file_name or "audio.mp3")
            if result:
                token_val, safe_name = result
                return {
                    "type": "file",
                    "payload": {"token": token_val, "name": safe_name}
                }
        
        # ГОЛОСОВЫЕ - через токен
        elif message.voice:
            file_data, filename = await downloader.download_file(message.voice.file_id)
            logger.info("🎤 [МЕДИА] Голосовое - загружаем токен")
            
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                return {
                    "type": "audio",
                    "payload": {"token": token}
                }
        
        # ДОКУМЕНТЫ - через токен
        elif message.document:
            file_name = message.document.file_name
            file_data, _ = await downloader.download_file(message.document.file_id)
            
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            # Проверяем, не изображение ли это
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                file_info = await downloader.get_file_info(message.document.file_id)
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
                logger.info(f"🖼️ [МЕДИА] Изображение как документ (ссылка)")
                return {
                    "type": "image",
                    "payload": {"url": file_url}
                }
            else:
                logger.info(f"📄 [МЕДИА] Документ: {file_name} - загружаем токен")
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token_val, safe_name = result
                    return {
                        "type": "file",
                        "payload": {"token": token_val, "name": safe_name}
                    }
    
    except Exception as e:
        logger.error(f"❌ Ошибка создания attachment: {e}")
        return None

async def process_large_video(message: types.Message):
    """Обрабатывает видео больше 50 МБ"""
    logger.info(f"🎥 [БОЛЬШОЕ ВИДЕО] Начинаем обработку")
    
    try:
        # 1. Скачиваем видео
        file_data, filename = await downloader.download_file(message.video.file_id)
        file_size_mb = len(file_data) / (1024 * 1024)
        
        # 2. Сохраняем во временный файл
        temp_file = f"/tmp/{filename}"
        with open(temp_file, 'wb') as f:
            f.write(file_data)
        
        # 3. Разбиваем на части
        logger.info(f"🔪 Разбиваем видео {file_size_mb:.1f} МБ на части")
        chunks = split_file_into_chunks(temp_file, chunk_size_mb=45)
        
        # 4. Загружаем каждую часть в MAX
        tokens = []
        for i, chunk_file in enumerate(chunks, 1):
            with open(chunk_file, 'rb') as f:
                chunk_data = f.read()
            
            logger.info(f"📤 Загрузка части {i}/{len(chunks)}")
            token = await uploader.upload_video(
                chunk_data, 
                f"{filename}.part{i:03d}",
                len(chunk_data)
            )
            if token:
                tokens.append(token)
            
            # Удаляем временный файл части
            os.remove(chunk_file)
        
        # 5. Отправляем все части в MAX как отдельные сообщения
        if tokens:
            for i, token in enumerate(tokens, 1):
                # Формируем подпись для каждой части
                part_caption = f"🎬 {filename} (часть {i}/{len(tokens)})"
                if message.caption:
                    part_caption = f"{message.caption}\n\n{part_caption}"
                
                attachments = [{
                    "type": "video",
                    "payload": {"token": token}
                }]
                
                await send_to_max(part_caption, attachments)
            
            # 6. Отправляем инструкцию по сборке
            instructions = (
                f"📹 **Видео разбито на {len(tokens)} частей**\n\n"
                f"**Как собрать оригинальное видео:**\n\n"
                f"**Windows:**\n"
                f"```\ncopy /b {filename}.part* {filename}\n```\n\n"
                f"**Linux/Mac:**\n"
                f"```\ncat {filename}.part* > {filename}\n```\n\n"
                f"После сборки удалите файлы частей."
            )
            
            # Отправляем инструкцию в тот же канал MAX
            await send_to_max(instructions)
            
            logger.info(f"✅ Большое видео обработано: {len(tokens)} частей")
        
        # Очистка
        os.remove(temp_file)
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки большого видео: {e}")

async def send_to_max(text: str, attachments: List[dict] = None, buttons: List[List[dict]] = None) -> Optional[str]:
    """Отправляет сообщение в MAX и возвращает URL"""
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text or " ",
        "format": "markdown"
    }
    
    if attachments:
        data["attachments"] = attachments
    
    if buttons:
        data["attachments"] = data.get("attachments", [])
        data["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
    
    logger.info("="*80)
    logger.info(f"📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст: {text[:100] if text else 'нет'}")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    message_url = result.get('message', {}).get('url')
                    logger.info(f"✅ УСПЕШНО: {message_url}")
                    return message_url
                else:
                    response = await resp.text()
                    logger.error(f"❌ Ошибка {resp.status}: {response}")
                    return None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None

async def process_album(album_id: str, messages: List[types.Message]):
    """Обрабатывает альбом из нескольких сообщений"""
    logger.info(f"📸 [АЛЬБОМ] Обработка {len(messages)} сообщений")
    
    all_attachments = []
    caption = messages[0].caption or ""
    caption_entities = messages[0].caption_entities
    
    for msg in messages:
        attachment = await create_attachment(msg)
        if attachment:
            all_attachments.append(attachment)
    
    if all_attachments:
        # Форматируем подпись
        formatted_text = format_text_with_entities(caption, caption_entities) if caption_entities else caption
        
        # Добавляем подпись о пересылке
        if messages[0].forward_date and messages[0].forward_from_chat:
            source = messages[0].forward_from_chat.title
            formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
        
        # Отправляем
        message_url = await send_to_max(formatted_text, all_attachments)
        
        # Сохраняем соответствие для редактирования
        for msg in messages:
            message_map[msg.message_id] = message_url

async def process_album_after_delay(album_id: str, delay: int = 2):
    """Обрабатывает альбом после небольшой задержки"""
    await asyncio.sleep(delay)
    
    async with album_lock:
        if album_id in albums:
            messages = albums.pop(album_id)
            await process_album(album_id, messages)

@dp.message()
async def forward(message: types.Message):
    """Основной обработчик"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    # Проверяем, является ли сообщение частью альбома
    if message.media_group_id:
        album_id = message.media_group_id
        logger.info(f"📸 [АЛЬБОМ] Часть альбома {album_id}")
        
        async with album_lock:
            if album_id not in albums:
                albums[album_id] = []
                asyncio.create_task(process_album_after_delay(album_id))
            
            albums[album_id].append(message)
            logger.info(f"📸 [АЛЬБОМ] В альбоме {len(albums[album_id])} сообщений")
        
        return
    
    # Обработка одиночных сообщений
    attachments = []
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    
    # ВЕТВЬ ДЛЯ ВИДЕО (с проверкой размера)
    if message.video:
        file_size_mb = message.video.file_size / (1024 * 1024)
        
        if file_size_mb <= 50:
            # Маленькое видео - старая схема
            logger.info(f"🎥 [ВИДЕО] Маленькое ({file_size_mb:.1f} МБ)")
            attachment = await create_attachment(message)
            if attachment:
                attachments.append(attachment)
        else:
            # Большое видео - новая схема с разбивкой
            await process_large_video(message)
            return  # Выходим, так как обработали отдельно
    
    # Для остальных типов медиа
    elif message.photo or message.audio or message.voice or message.document:
        attachment = await create_attachment(message)
        if attachment:
            attachments.append(attachment)
    
    # Извлекаем кнопки
    buttons = extract_buttons(message)
    
    # Форматируем текст
    formatted_text = format_text_with_entities(text, entities) if entities else text
    
    # Добавляем подпись о пересылке
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
    
    # Отправляем
    if attachments or formatted_text:
        message_url = await send_to_max(formatted_text, attachments, buttons)
        if message_url:
            message_map[message.message_id] = message_url

@dp.edited_message()
async def edit_message(message: types.Message):
    """Обработчик редактирования сообщений"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    if message.message_id not in message_map:
        logger.warning(f"⚠️ Нет информации об оригинальном сообщении {message.message_id}")
        return
    
    max_url = message_map[message.message_id]
    # Извлекаем message_id из URL (последняя часть после слеша)
    message_id = max_url.split('/')[-1]
    
    logger.info(f"✏️ Редактирование сообщения {message.message_id} -> {max_url}")
    
    # Получаем новый текст и форматирование
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    formatted_text = format_text_with_entities(text, entities) if entities else text
    
    # ПРАВИЛЬНЫЙ ЭНДПОИНТ согласно документации MAX
    url = f"https://platform-api.max.ru/messages?message_id={message_id}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": formatted_text,
        "format": "markdown"
    }
    
    # Для медиа-сообщений attachments можно не трогать
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Сообщение обновлено")
                else:
                    response = await resp.text()
                    logger.error(f"❌ Ошибка редактирования {resp.status}: {response}")
        except Exception as e:
            logger.error(f"❌ Ошибка при редактировании: {e}")

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **MAX ПЕРЕСЫЛЬЩИК (ФИНАЛЬНАЯ ВЕРСИЯ)**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 📝 Текст с полным форматированием\n"
        "• 🖼️ Фото\n"
        "• 🎥 Видео (до 50 МБ - обычная схема, >50 МБ - разбивка на части)\n"
        "• 🎵 Аудио\n"
        "• 🎤 Голосовые\n"
        "• 📄 PDF, DOC, XLS\n"
        "• 🔗 Кнопки-ссылки\n"
        "• 📸 Альбомы\n"
        "• ✏️ Редактирование (24 часа)\n\n"
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
    logger.info("🚀 ЗАПУСК ФИНАЛЬНОЙ ВЕРСИИ БОТА")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
