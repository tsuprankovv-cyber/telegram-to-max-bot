# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.text_decorations import html_decoration
from aiogram.client.session.aiohttp import AiohttpSession
from typing import List, Tuple, Optional, Dict, Any

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '').strip()
MAX_TOKEN = os.getenv('MAX_TOKEN', '').strip()
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID', '').strip()
DEBUG_FORMATTING = os.getenv('DEBUG_FORMATTING', 'false').lower() == 'true'
PROXY_URL = os.getenv('PROXY_URL', '').strip()

# === 🔹 СПИСОК БЕСПЛАТНЫХ ПРОКСИ ===
FREE_PROXIES = [
    "http://51.159.113.50:3128",
    "http://51.159.113.51:3128",
    "http://51.159.113.52:3128",
    "http://185.162.230.80:80",
    "http://185.162.230.81:80",
    "http://185.162.230.82:80",
    "http://185.162.230.83:80",
    "http://103.152.112.162:80",
    "http://103.152.112.145:80",
    "http://47.88.31.85:80",
    "http://47.91.95.123:8080",
    "http://103.167.135.110:80",
    "http://103.167.135.111:80",
    "http://185.217.136.235:1337",
    "http://185.217.136.239:1337",
]

logger.info("="*80)
logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (TELEGRAM -> MAX)")
logger.info(f"👥 TG Group: {TELEGRAM_GROUP_ID}")
logger.info(f"📢 MAX Channel: {MAX_CHANNEL_ID}")
logger.info(f"🔍 DEBUG_FORMATTING: {DEBUG_FORMATTING}")
logger.info(f"🔹 ПРОКСИ: {PROXY_URL if PROXY_URL else 'Будет использован список бесплатных'}")

# 🔹 ПРОВЕРКА ПЕРЕМЕННЫХ
missing = []
if not TELEGRAM_TOKEN: missing.append('TELEGRAM_TOKEN')
if not TELEGRAM_GROUP_ID: missing.append('TELEGRAM_GROUP_ID')
if not MAX_TOKEN: missing.append('MAX_TOKEN')
if not MAX_CHANNEL_ID: missing.append('MAX_CHANNEL_ID')

if missing:
    logger.error("❌ ОТСУТСТВУЮТ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
    for var in missing:
        logger.error(f"   - {var}")
    raise ValueError(f"Missing: {', '.join(missing)}")

logger.info("✅ Все переменные установлены")
logger.info("="*80)

# === 🔹 ФУНКЦИЯ ПРОВЕРКИ ПРОКСИ ===
async def test_proxy(proxy_url: str) -> bool:
    """Проверяет работает ли прокси"""
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get('https://api.telegram.org', proxy=proxy_url) as resp:
                return resp.status == 200
    except:
        return False

# === 🔹 ФУНКЦИЯ ПОИСКА РАБОЧЕГО ПРОКСИ ===
async def find_working_proxy() -> Optional[str]:
    """Перебирает список прокси и возвращает первый рабочий"""
    
    if PROXY_URL:
        logger.info(f"🔍 Проверка пользовательского прокси: {PROXY_URL}")
        if await test_proxy(PROXY_URL):
            logger.info(f"✅ Пользовательский прокси работает!")
            return PROXY_URL
        else:
            logger.warning(f"⚠️ Пользовательский прокси НЕ работает, пробуем бесплатные...")
    
    logger.info(f"🔍 Перебор бесплатных прокси ({len(FREE_PROXIES)} шт)...")
    
    for i, proxy in enumerate(FREE_PROXIES, 1):
        logger.debug(f"📍 Прокси {i}/{len(FREE_PROXIES)}: {proxy}")
        if await test_proxy(proxy):
            logger.info(f"✅ Найден рабочий прокси: {proxy}")
            return proxy
    
    logger.warning("⚠️ Ни один прокси не работает!")
    return None

# === 🔹 СОЗДАЁМ DP СРАЗУ (до декораторов!) ===
dp = Dispatcher()

# === ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ===
telegram_bot = None
uploader = None
downloader = None

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
    return ''.join(TRANSLIT_DICT.get(char, char) for char in text)

def safe_filename(filename: str) -> str:
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    name = transliterate(name)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return f"{name or 'file'}.{ext}" if ext else (name or 'file')

# === ИЗВЛЕЧЕНИЕ КНОПОК ===
def extract_buttons(message: types.Message) -> list:
    buttons = []
    if message.reply_markup and hasattr(message.reply_markup, 'inline_keyboard'):
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
    return buttons

# === ФОРМАТИРОВАНИЕ ТЕКСТА ===
def format_text(telegram_text: str, entities: list, message_id: int = None) -> str:
    msg_prefix = f"[MSG {message_id}]" if message_id else ""
    
    if not telegram_text:
        logger.info(f"{msg_prefix} 📭 Пустой текст")
        return ""
    
    if not entities:
        logger.info(f"{msg_prefix} 🔤 Текст без сущностей")
        return telegram_text

    logger.info(f"{msg_prefix} 📝 Форматирование: {len(telegram_text)} символов, {len(entities)} сущностей")
    
    try:
        result = html_decoration.unparse(telegram_text, entities)
        logger.info(f"{msg_prefix} ✅ Форматирование успешно")
        return result
    except Exception as e:
        logger.exception(f"{msg_prefix} ❌ Ошибка форматирования: {e}")
        return telegram_text

# === ЗАГРУЗКА МЕДИА ===
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
            "photo_ok": 0, "photo_failed": 0
        }

    async def ensure_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=120)
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("🔗 Создана сессия MediaUploader")

    async def create_upload(self, media_type: str) -> dict:
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.debug(f"📤 POST {url} type={media_type}")
        try:
            async with self.session.post(url, headers=headers, params=params) as resp:
                resp_text = await resp.text()
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"❌ Ошибка create_upload: {resp.status} - {resp_text[:200]}")
                    return {}
        except Exception as e:
            logger.exception(f"❌ Исключение create_upload: {e}")
            return {}

    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.debug(f"📤 Загрузка: {filename} ({len(file_data)} байт)")
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        try:
            async with self.session.post(upload_url, data=data) as resp:
                logger.debug(f"📥 Ответ: {resp.status}")
                return resp.status == 200
        except Exception as e:
            logger.exception(f"❌ Исключение upload_file_only: {e}")
            return False

    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        try:
            async with self.session.post(upload_url, data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    token = result.get('token')
                    logger.debug(f"✅ Токен: {token[:20] if token else None}...")
                    return token
                else:
                    logger.error(f"❌ Ошибка загрузки: {resp.status}")
                    return None
        except Exception as e:
            logger.exception(f"❌ Исключение upload_file_and_get_token: {e}")
            return None

    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎬 Видео: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                logger.error(f"❌ Нет token/url: {upload_info}")
                self.stats["video_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1)
                self.stats["video_ok"] += 1
                logger.info(f"✅ Видео: {safe_name}")
                return token
            else:
                self.stats["video_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение upload_video: {e}")
            self.stats["video_failed"] += 1
            return None

    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"📄 Документ: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["documents_failed"] += 1
                return None
                
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            if token:
                self.stats["documents_ok"] += 1
                logger.info(f"✅ Документ: {safe_name}")
                return (token, safe_name)
            else:
                self.stats["documents_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение upload_document: {e}")
            self.stats["documents_failed"] += 1
            return None

    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎵 Аудио: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["audio_failed"] += 1
                return None
                
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            if token:
                self.stats["audio_ok"] += 1
                logger.info(f"✅ Аудио: {safe_name}")
                return (token, safe_name)
            else:
                self.stats["audio_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение upload_audio: {e}")
            self.stats["audio_failed"] += 1
            return None

    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎤 Голосовое: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1)
                self.stats["voice_ok"] += 1
                logger.info(f"✅ Голосовое: {safe_name}")
                return token
            else:
                self.stats["voice_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение upload_voice: {e}")
            self.stats["voice_failed"] += 1
            return None

class TelegramDownloader:
    def __init__(self, token: str, proxy: str = None):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.proxy = proxy
        self.session = None

    async def ensure_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=60)
            if self.proxy:
                self.session = aiohttp.ClientSession(timeout=timeout, proxy=self.proxy)
            else:
                self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info(f"🔗 Создана сессия TelegramDownloader{' с прокси' if self.proxy else ''}")

    async def get_file_info(self, file_id: str) -> dict:
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        logger.debug(f"📤 FileInfo: {file_id[:20]}...")
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            else:
                text = await resp.text()
                raise Exception(f"Ошибка getInfo: {resp.status} - {text}")

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        await self.ensure_session()
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        url = f"{self.file_url}/{file_path}"
        
        logger.info(f"📥 Скачать: {filename} ({file_info.get('file_size', '?')} байт)")
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                logger.info(f"✅ Скачано: {filename} ({len(data)} байт)")
                return (data, filename)
            else:
                raise Exception(f"Ошибка download: {resp.status}")

# === ОТПРАВКА В MAX ===
async def send_to_max(text: str, attachments: List[dict] = None):
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }

    data = {
        "text": text or " ",
        "format": "html"
    }

    if attachments:
        data["attachments"] = attachments

    logger.info(f"📤 MAX: текст={len(text)} симв., вложений={len(attachments) if attachments else 0}")
    
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                if resp.status == 200:
                    logger.info("✅ Отправлено в MAX")
                    return True
                else:
                    logger.error(f"❌ MAX {resp.status}: {response_text[:500]}")
                    return False
    except Exception as e:
        logger.exception(f"❌ Исключение send_to_max: {e}")
        return False

# === ОБРАБОТКА МЕДИА ===
async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
    attachments = []
    text = message.caption or ""
    
    try:
        if message.photo:
            logger.info("🖼️ Фото")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"{downloader.file_url}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1

        elif message.video:
            logger.info("🎥 Видео")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({"type": "video", "payload": {"token": token}})

        elif message.audio:
            logger.info("🎵 Аудио")
            file_data, _ = await downloader.download_file(message.audio.file_id)
            original_name = message.audio.file_name or "audio.mp3"
            result = await uploader.upload_audio(file_data, original_name)
            if result:
                token, safe_name = result
                attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})

        elif message.voice:
            logger.info("🎤 Голосовое")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({"type": "audio", "payload": {"token": token}})

        elif message.document:
            file_name = message.document.file_name
            logger.info(f"📄 Документ: {file_name}")
            file_data, _ = await downloader.download_file(message.document.file_id)
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt']:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})
            elif ext in ['mp4', 'mov', 'avi']:
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({"type": "video", "payload": {"token": token}})
            elif ext in ['mp3', 'wav', 'ogg']:
                result = await uploader.upload_audio(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})
            else:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})

    except Exception as e:
        logger.exception(f"❌ Ошибка process_media_message: {e}")
        
    return text, attachments

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
@dp.message()
async def forward(message: types.Message):
    if str(message.chat.id) != str(TELEGRAM_GROUP_ID):
        logger.debug(f"🚫 Чужой чат: {message.chat.id} (ожидалось {TELEGRAM_GROUP_ID})")
        return

    logger.info(f"📨 MSG {message.message_id} из {message.chat.id}")
    
    buttons = extract_buttons(message)
    attachments = []
    final_text = ""
    
    if message.text:
        raw_text = message.text
        entities = message.entities or []
        logger.info("📝 Текст")
    elif message.caption:
        raw_text = message.caption
        entities = message.caption_entities or []
        logger.info("📝 Caption")
    else:
        raw_text = ""
        entities = []
        logger.info("📝 Без текста")

    if raw_text:
        final_text = format_text(raw_text, entities, message_id=message.message_id)
        logger.info(f"✍️ Текст: {len(final_text)} симв.")
    
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title or "Неизвестный источник"
        final_text = f"📢 Переслано из {source}:\n\n{final_text}"
        logger.info(f"🔁 Префикс: {source}")

    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Медиа")
        _, media_attachments = await process_media_message(message)
        attachments.extend(media_attachments)
        
        if not attachments and not final_text:
            logger.warning("⚠️ Нет текста и медиа — пропускаем")
            return 

    if buttons:
        attachments.append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
        logger.info(f"🔘 Кнопки: {len(buttons)} рядов")

    if final_text or attachments:
        success = await send_to_max(final_text, attachments if attachments else None)
        if success:
            logger.info(f"✅ MSG {message.message_id} переслано")
        else:
            logger.error(f"❌ MSG {message.message_id} НЕ переслано")
    else:
        logger.warning("⚠️ Нечего отправлять")

# === КОМАНДЫ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("✅ Бот запущен.\nИспользуйте /stats для статистики.")
    logger.info(f"👤 /start от {message.from_user.id}")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    text = (
        f"📊 **СТАТИСТИКА:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']} | ❌ {stats['photo_failed']}"
    )
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"👤 /stats от {message.from_user.id}")

# === ОЧИСТКА ===
async def cleanup():
    logger.info("🧹 Закрытие сессий...")
    if downloader and downloader.session:
        await downloader.session.close()
    if uploader and uploader.session:
        await uploader.session.close()
    if telegram_bot and telegram_bot.session:
        await telegram_bot.session.close()
    logger.info("✅ Сессии закрыты")

# === ЗАПУСК ===
async def main():
    global telegram_bot, uploader, downloader
    
    # 🔹 1. Находим рабочий прокси
    proxy = await find_working_proxy()
    
    # 🔹 2. Создаём сессию и бота
    timeout = aiohttp.ClientTimeout(total=120)
    if proxy:
        session = AiohttpSession(timeout=timeout, proxy=proxy)
        logger.info(f"✅ Сессия создана с прокси")
    else:
        session = AiohttpSession(timeout=timeout)
        logger.warning("⚠️ Сессия создана БЕЗ прокси")
    
    telegram_bot = Bot(token=TELEGRAM_TOKEN, session=session)
    
    # 🔹 3. Инициализируем глобальные объекты
    uploader = MediaUploader(MAX_TOKEN)
    downloader = TelegramDownloader(TELEGRAM_TOKEN, proxy)
    
    # 🔹 4. Webhook — ОПЦИОНАЛЬНО
    try:
        logger.info("🔌 Попытка удалить webhook...")
        await asyncio.wait_for(
            telegram_bot.delete_webhook(drop_pending_updates=True),
            timeout=60
        )
        logger.info("✅ Webhook удалён")
    except asyncio.TimeoutError:
        logger.warning("⏰ Timeout при удалении webhook — пропускаем")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить webhook: {e} — продолжаем работу")
    
    # 🔹 5. Проверка соединения
    try:
        logger.info("🔍 Проверка соединения с Telegram...")
        me = await telegram_bot.get_me()
        logger.info(f"✅ Бот авторизован: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться к Telegram: {e}")
        logger.error("💡 Попробуйте перезапустить бота — прокси переберутся заново")
        raise
    
    logger.info("✨ Polling запущен...")
    try:
        await dp.start_polling(telegram_bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Остановка")
    finally:
        await cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
