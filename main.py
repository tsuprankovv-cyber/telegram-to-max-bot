import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
import sys
import unicodedata
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional, Dict, Any

# === НАСТРОЙКА МАКСИМАЛЬНОГО ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
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

# === ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ КНОПОК ===
def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
        logger.info(f"🔘 Найдены inline кнопки")
        
        for row_idx, row in enumerate(message.reply_markup.inline_keyboard):
            button_row = []
            for btn_idx, btn in enumerate(row):
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
                    logger.debug(f"   Кнопка {row_idx+1}.{btn_idx+1}: '{btn.text}' -> {btn.url}")
            if button_row:
                buttons.append(button_row)
        
        logger.info(f"✅ Найдено {len(buttons)} рядов кнопок")
    
    return buttons

# === ФУНКЦИЯ ДЛЯ ПРОВЕРКИ 100% СОВПАДЕНИЯ ===
def verify_exact_match(original: str, formatted: str) -> Tuple[bool, str, List[str]]:
    """
    Проверяет, совпадает ли очищенный отформатированный текст с оригиналом на 100%
    Возвращает (успех, очищенный текст, список расхождений)
    """
    logger.debug("\n🔍 ПРОВЕРКА 100% СОВПАДЕНИЯ:")
    
    # Удаляем все теги из форматированного текста
    clean = re.sub(r'<[^>]+>', '', formatted)
    
    differences = []
    
    if clean == original:
        logger.debug("✅ Текст совпадает на 100%!")
        return True, clean, differences
    
    # Если не совпадает, ищем расхождения
    logger.warning("⚠️ Текст НЕ совпадает! Ищем расхождения...")
    
    # Сравниваем посимвольно
    min_len = min(len(clean), len(original))
    for i in range(min_len):
        if clean[i] != original[i]:
            diff = f"Позиция {i}: '{clean[i]}' vs '{original[i]}'"
            differences.append(diff)
            logger.warning(f"  {diff}")
            break
    
    if len(clean) != len(original):
        diff = f"Разная длина: {len(clean)} vs {len(original)}"
        differences.append(diff)
        logger.warning(f"  {diff}")
    
    return False, clean, differences

# === ФУНКЦИЯ ДЛЯ ПРИМЕНЕНИЯ ФОРМАТИРОВАНИЯ К БОЛВАНКЕ ===
def apply_formatting_to_blank(blank_text: str, fragments: List[Dict]) -> str:
    """
    Применяет форматирование к чистой болванке
    """
    logger.debug("\n✏️ ПРИМЕНЕНИЕ ФОРМАТИРОВАНИЯ К БОЛВАНКЕ:")
    
    result = blank_text
    
    for i, f in enumerate(fragments):
        # Ищем точное вхождение фрагмента
        pos = result.find(f['text'])
        
        if pos != -1:
            # Показываем контекст для уверенности
            context_start = max(0, pos - 20)
            context_end = min(len(result), pos + len(f['text']) + 20)
            context = result[context_start:context_end]
            logger.debug(f"\n  Фрагмент {i} ({f['type']}):")
            logger.debug(f"    Текст: '{f['text'][:50]}...'")
            logger.debug(f"    Позиция: {pos}")
            logger.debug(f"    Контекст: ...{context}...")
            
            # Применяем соответствующие теги
            if f['type'] == "bold":
                replacement = f"<b>{f['text']}</b>"
                logger.debug(f"    🔧 Применяем жирный")
            elif f['type'] == "italic":
                replacement = f"<i>{f['text']}</i>"
                logger.debug(f"    🔧 Применяем курсив")
            elif f['type'] == "underline":
                replacement = f"<u>{f['text']}</u>"
            elif f['type'] == "strikethrough":
                replacement = f"<s>{f['text']}</s>"
            elif f['type'] == "code":
                replacement = f"<code>{f['text']}</code>"
            elif f['type'] == "pre":
                replacement = f"<pre>{f['text']}</pre>"
            elif f['type'] == "blockquote":
                replacement = f"<blockquote>{f['text']}</blockquote>"
            elif f['type'] == "text_link":
                replacement = f'<a href="{f["url"]}">{f["text"]}</a>'
                logger.debug(f"    🔗 Применяем ссылку")
            else:
                logger.debug(f"    ⏭️ Неподдерживаемый тип: {f['type']}")
                continue
            
            # Применяем замену
            result = result[:pos] + replacement + result[pos + len(f['text']):]
            logger.debug(f"    ✅ Применено")
        else:
            logger.error(f"\n  ❌ Фрагмент {i} НЕ НАЙДЕН в тексте!")
            logger.error(f"     Искали: '{f['text'][:50]}...'")
    
    return result

# === ГЛАВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ - ВАШ АЛГОРИТМ ===
def format_text(telegram_text: str, entities: list) -> str:
    """
    ВАШ ИДЕАЛЬНЫЙ АЛГОРИТМ:
    
    ШАГ 1: Получаем из Telegram текст и entities
    ШАГ 2: Создаем чистую болванку (тот же текст, но без форматирования)
    ШАГ 3: Из entities извлекаем фрагменты, которые были отформатированы
    ШАГ 4: Находим эти фрагменты в болванке
    ШАГ 5: Применяем к ним форматирование
    ШАГ 6: Проверяем 100% совпадение с оригиналом
    """
    logger.debug(f"\n{'='*60}")
    logger.debug(f"🔍 ВАШ АЛГОРИТМ: ФОРМАТИРОВАНИЕ С ПРОВЕРКОЙ 100%")
    logger.debug(f"📝 Исходный текст из Telegram: {repr(telegram_text[:200])}...")
    
    # ШАГ 1: Извлекаем отформатированные фрагменты из Telegram
    fragments = []
    logger.debug(f"\n📋 ИЗВЛЕЧЕНИЕ ФРАГМЕНТОВ ИЗ TELEGRAM:")
    
    for i, e in enumerate(entities):
        # Проверяем границы
        if e.offset + e.length > len(telegram_text):
            logger.warning(f"  ⚠️ Entity {i} выходит за границы, корректируем")
            e.length = len(telegram_text) - e.offset
        
        fragment = telegram_text[e.offset:e.offset + e.length]
        
        fragments.append({
            'id': i,
            'type': e.type,
            'text': fragment,
            'url': getattr(e, 'url', None),
            'telegram_start': e.offset,
            'telegram_end': e.offset + e.length
        })
        logger.debug(f"  Фрагмент {i}: {e.type} [{e.offset}:{e.offset+e.length}] '{fragment[:50]}...'")
    
    # ШАГ 2: Создаем чистую болванку (тот же текст, но без форматирования)
    blank_text = telegram_text
    logger.debug(f"\n📄 ЧИСТАЯ БОЛВАНКА (без форматирования):")
    logger.debug(f"  {blank_text[:100]}...")
    
    # ШАГ 3: Применяем форматирование к болванке
    formatted_text = apply_formatting_to_blank(blank_text, fragments)
    
    # ШАГ 4: Проверяем 100% совпадение
    match_ok, clean_text, differences = verify_exact_match(telegram_text, formatted_text)
    
    if match_ok:
        logger.debug("\n✅ ИТОГ: 100% СОВПАДЕНИЕ С ОРИГИНАЛОМ!")
        return formatted_text
    else:
        logger.error("\n❌ ИТОГ: ТЕКСТ ИЗМЕНИЛСЯ! Что-то пошло не так.")
        logger.error(f"   Оригинал: {telegram_text[:100]}...")
        logger.error(f"   Очищенный: {clean_text[:100]}...")
        
        # ВАЖНО: Если текст изменился, значит алгоритм сработал неправильно
        # Возвращаем оригинал без форматирования, чтобы не испортить
        return telegram_text

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
            "photo_ok": 0
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
    
    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            upload_info = await self.create_upload("video")
            
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["video_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(2)
                self.stats["video_ok"] += 1
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
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
            
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(2)
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
    
    logger.info("="*80)
    logger.info(f"📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст: {text[:100] if text else 'нет'}")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    logger.debug(f"📦 Полные данные запроса: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                logger.info(f"📥 Статус ответа: {resp.status}")
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    logger.error(f"❌ Ошибка {resp.status}: {response_text[:200]}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
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
            token = await uploader.upload_video(file_data, filename)
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
            
            elif ext in ['mp4', 'mov', 'avi']:
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "video",
                        "payload": {"token": token}
                    })
            
            elif ext in ['mp3', 'wav', 'ogg']:
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

@dp.message()
async def forward(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    logger.info(f"📝 Есть ли текст: {'да' if message.text or message.caption else 'нет'}")
    logger.info(f"📊 Entities в тексте: {len(message.entities or [])}")
    logger.info(f"📊 Entities в подписи: {len(message.caption_entities or [])}")
    
    # Извлекаем кнопки
    buttons = extract_buttons(message)
    
    # ========== ТЕКСТОВЫЕ СООБЩЕНИЯ ==========
    if message.text and not message.photo and not message.video and not message.audio and not message.voice and not message.document:
        logger.info("📝 Чисто текстовое сообщение")
        text = message.text
        entities = message.entities or []
        
        logger.info(f"📝 Исходный текст из Telegram: {text[:100]}...")
        
        # Применяем ВАШ АЛГОРИТМ
        formatted_text = format_text(text, entities)
        logger.info(f"📝 Текст после форматирования: {formatted_text[:100]}...")
        
        # Добавляем кнопки если есть
        attachments = []
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
        
        # Добавляем подпись о пересылке
        if message.forward_date and message.forward_from_chat:
            formatted_text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{formatted_text}"
            logger.info(f"🔄 Добавлена подпись о пересылке")
        
        await send_to_max(formatted_text, attachments if attachments else None)
        return
    
    # ========== МЕДИА СООБЩЕНИЯ ==========
    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Медиа сообщение")
        text, attachments = await process_media_message(message)
        
        if not attachments:
            logger.warning("⚠️ Нет вложений")
            return
        
        # Добавляем кнопки
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
            logger.info(f"🔘 Добавлено {len(buttons)} рядов кнопок")
        
        # Применяем ВАШ АЛГОРИТМ к подписи
        if message.caption and message.caption_entities:
            logger.info(f"📝 Форматируем подпись по вашему алгоритму: {text[:100]}...")
            text = format_text(text, message.caption_entities)
            logger.info(f"📝 После форматирования: {text[:100]}...")
        elif message.caption:
            logger.info(f"📝 Подпись без форматирования: {text[:100]}...")
        else:
            logger.info("📝 Подпись отсутствует")
        
        # Добавляем подпись о пересылке
        if message.forward_date and message.forward_from_chat:
            source = message.forward_from_chat.title
            text = f"📢 Переслано из {source}:\n\n{text}"
            logger.info(f"🔄 Добавлена подпись о пересылке из {source}")
        
        await send_to_max(text, attachments)
        return
    
    logger.warning(f"⚠️ Неподдерживаемый тип сообщения: {message.content_type}")

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **БОТ С ВАШИМ АЛГОРИТМОМ**\n\n"
        "📋 **ПОСЛЕДОВАТЕЛЬНОСТЬ:**\n"
        "1. 📄 Чистая болванка (текст без форматирования)\n"
        "2. 📋 Извлечение фрагментов из Telegram\n"
        "3. 🔍 Поиск фрагментов в болванке\n"
        "4. ✏️ Применение форматирования\n"
        "5. ✅ Проверка 100% совпадения\n\n"
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
        f"🖼️ Фото: ✅ {stats['photo_ok']}"
    )

async def cleanup():
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()

async def main():
    logger.info("✨✨✨ ЗАПУСК БОТА С ВАШИМ АЛГОРИТМОМ ✨✨✨")
    logger.info("✅ Чистая болванка из текста Telegram")
    logger.info("✅ Поиск фрагментов по точному совпадению")
    logger.info("✅ Проверка 100% совпадения")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
