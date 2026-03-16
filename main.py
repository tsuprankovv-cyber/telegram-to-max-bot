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

# === ФУНКЦИЯ ДЛЯ ОПРЕДЕЛЕНИЯ ШИРИНЫ СИМВОЛА (ДЛЯ ПОДСЧЕТА) ===
def get_char_width(char: str) -> int:
    """
    Определяет ширину символа для подсчета
    """
    char_code = ord(char)
    
    # Вариационные селекторы
    if 0xFE00 <= char_code <= 0xFE0F:
        return 0
    
    # Специальные символы
    special = {
        '—': 2, '–': 2, '…': 2, '«': 1, '»': 1, '‑': 1
    }
    if char in special:
        return special[char]
    
    # Эмодзи
    emoji_ranges = [
        (0x1F300, 0x1F9FF), (0x2600, 0x26FF), (0x2700, 0x27BF),
        (0x1F1E6, 0x1F1FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF)
    ]
    for start, end in emoji_ranges:
        if start <= char_code <= end:
            return 2
    
    return 1

# === ФУНКЦИЯ ДЛЯ РАСЧЕТА СМЕЩЕНИЙ ===
def calculate_offsets(text: str) -> Dict[int, int]:
    """
    Рассчитывает смещение для каждой позиции из-за эмодзи
    """
    offsets = {}
    tg_pos = 0
    py_pos = 0
    
    logger.debug("📊 Расчет смещений:")
    for py_pos, char in enumerate(text):
        offsets[py_pos] = tg_pos
        width = get_char_width(char)
        if width != 1:
            logger.debug(f"  {py_pos}: '{char}' -> tg_pos={tg_pos}, ширина={width}")
        tg_pos += width
    
    logger.debug(f"📊 Итоговое смещение: {tg_pos - len(text)}")
    return offsets

# === ФУНКЦИЯ ДЛЯ КОРРЕКЦИИ ENTITIES ===
def correct_entities(text: str, entities: list) -> list:
    """
    Корректирует entities с учетом эмодзи
    """
    logger.debug("\n🔧 КОРРЕКЦИЯ ENTITIES:")
    
    offsets = calculate_offsets(text)
    corrected = []
    
    for i, e in enumerate(entities):
        # Корректируем начало
        corrected_start = None
        for py_pos, tg_pos in offsets.items():
            if tg_pos >= e.offset:
                corrected_start = py_pos
                break
        
        if corrected_start is None:
            logger.warning(f"  ⚠️ Entity {i} не найден")
            continue
        
        # Корректируем конец
        tg_end = e.offset + e.length
        corrected_end = None
        for py_pos, tg_pos in offsets.items():
            if tg_pos >= tg_end:
                corrected_end = py_pos
                break
        
        if corrected_end is None:
            corrected_end = len(text)
        
        # Проверка границ
        if corrected_end > len(text):
            corrected_end = len(text)
        
        fragment = text[corrected_start:corrected_end]
        logger.debug(f"  Entity {i}: {e.type} [{e.offset}:{e.offset+e.length}] -> [{corrected_start}:{corrected_end}] '{fragment}'")
        
        # Создаем новый entity
        class CorrectedEntity:
            pass
        
        new_e = CorrectedEntity()
        new_e.type = e.type
        new_e.offset = corrected_start
        new_e.length = corrected_end - corrected_start
        new_e.url = getattr(e, 'url', None)
        
        corrected.append(new_e)
    
    return corrected

# === ФУНКЦИЯ ДЛЯ ВАЛИДАЦИИ ФОРМАТИРОВАНИЯ ===
def validate_formatting(original_text: str, original_entities: list, formatted_text: str) -> Dict[str, Any]:
    """
    Проверяет, правильно ли применилось форматирование
    """
    logger.debug("\n🔎 ВАЛИДАЦИЯ ФОРМАТИРОВАНИЯ:")
    
    results = {
        'passed': True,
        'errors': [],
        'warnings': [],
        'details': {}
    }
    
    for i, e in enumerate(original_entities):
        # Получаем ожидаемый фрагмент
        expected = original_text[e.offset:e.offset + e.length]
        
        # Определяем теги
        if e.type == "bold":
            tag = 'b'
        elif e.type == "italic":
            tag = 'i'
        elif e.type == "underline":
            tag = 'u'
        elif e.type == "strikethrough":
            tag = 's'
        elif e.type == "code":
            tag = 'code'
        elif e.type == "pre":
            tag = 'pre'
        elif e.type == "blockquote":
            tag = 'blockquote'
        elif e.type == "text_link":
            tag = 'a'
        else:
            continue
        
        # Ищем в форматированном тексте
        pattern = f"<{tag}[^>]*>(.*?)</{tag}>"
        matches = re.findall(pattern, formatted_text, re.DOTALL)
        
        found = False
        for match in matches:
            if expected in match:
                found = True
                results['details'][f'entity_{i}'] = {
                    'type': e.type,
                    'expected': expected,
                    'found': match,
                    'status': 'OK'
                }
                logger.debug(f"  ✅ Entity {i} ({e.type}): найден '{match[:50]}...'")
                break
        
        if not found:
            # Ищем без учета регистра и пробелов
            expected_clean = re.sub(r'\s+', ' ', expected).strip()
            for match in matches:
                match_clean = re.sub(r'\s+', ' ', match).strip()
                if expected_clean in match_clean:
                    found = True
                    results['warnings'].append(f"Entity {i} найден с расхождениями в пробелах")
                    logger.debug(f"  ⚠️ Entity {i} найден с расхождениями")
                    break
            
            if not found:
                results['passed'] = False
                results['errors'].append(f"Entity {i} ({e.type}) не найден: '{expected}'")
                logger.error(f"  ❌ Entity {i} не найден!")
    
    return results

# === ФУНКЦИЯ ДЛЯ РУЧНОГО ФОРМАТИРОВАНИЯ ===
def manual_format(text: str, entities: list) -> str:
    """
    Ручное форматирование с поиском по тексту
    """
    logger.debug("\n✋ РУЧНОЕ ФОРМАТИРОВАНИЕ:")
    
    result = text
    
    for i, e in enumerate(entities):
        expected = text[e.offset:e.offset + e.length]
        logger.debug(f"  Поиск '{expected[:50]}...'")
        
        # Ищем точное вхождение
        pos = result.find(expected)
        if pos != -1:
            if e.type == "bold":
                replacement = f"<b>{expected}</b>"
            elif e.type == "italic":
                replacement = f"<i>{expected}</i>"
            elif e.type == "text_link":
                replacement = f'<a href="{e.url}">{expected}</a>'
            else:
                continue
            
            result = result[:pos] + replacement + result[pos + len(expected):]
            logger.debug(f"  ✅ Применено на позиции {pos}")
        else:
            # Ищем без учета пробелов
            expected_clean = re.sub(r'\s+', ' ', expected).strip()
            text_clean = re.sub(r'\s+', ' ', result).strip()
            
            clean_pos = text_clean.find(expected_clean)
            if clean_pos != -1:
                logger.debug(f"  ⚠️ Найдено с расхождениями в пробелах")
    
    return result

# === ОСНОВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ ===
def format_text(text: str, entities: list) -> str:
    """
    МНОГОУРОВНЕВАЯ СИСТЕМА ФОРМАТИРОВАНИЯ:
    1. Прямое форматирование
    2. Проверка результатов
    3. Коррекция при ошибках
    """
    logger.debug(f"\n{'='*60}")
    logger.debug(f"🔍 МНОГОУРОВНЕВОЕ ФОРМАТИРОВАНИЕ")
    
    # === УРОВЕНЬ 1: КОРРЕКЦИЯ ENTITIES ===
    corrected_entities = correct_entities(text, entities)
    
    # === УРОВЕНЬ 2: ПРЯМОЕ ФОРМАТИРОВАНИЕ ===
    logger.debug("\n📝 ПРЯМОЕ ФОРМАТИРОВАНИЕ:")
    
    # Сортируем от конца к началу
    sorted_entities = sorted(corrected_entities, key=lambda e: e.offset + e.length, reverse=True)
    result = text
    
    for e in sorted_entities:
        # Проверка границ
        if e.offset + e.length > len(result):
            logger.warning(f"  ⚠️ Entity выходит за границы, корректируем")
            e.length = len(result) - e.offset
        
        fragment = result[e.offset:e.offset + e.length]
        
        if e.type == "bold":
            result = result[:e.offset] + f"<b>{fragment}</b>" + result[e.offset + e.length:]
            logger.debug(f"  ✅ bold: '{fragment[:50]}...'")
        elif e.type == "italic":
            result = result[:e.offset] + f"<i>{fragment}</i>" + result[e.offset + e.length:]
            logger.debug(f"  ✅ italic: '{fragment[:50]}...'")
        elif e.type == "underline":
            result = result[:e.offset] + f"<u>{fragment}</u>" + result[e.offset + e.length:]
        elif e.type == "strikethrough":
            result = result[:e.offset] + f"<s>{fragment}</s>" + result[e.offset + e.length:]
        elif e.type == "code":
            result = result[:e.offset] + f"<code>{fragment}</code>" + result[e.offset + e.length:]
        elif e.type == "pre":
            result = result[:e.offset] + f"<pre>{fragment}</pre>" + result[e.offset + e.length:]
        elif e.type == "text_link":
            result = result[:e.offset] + f'<a href="{e.url}">{fragment}</a>' + result[e.offset + e.length:]
            logger.debug(f"  🔗 link: '{fragment[:50]}...'")
        elif e.type == "blockquote":
            result = result[:e.offset] + f"<blockquote>{fragment}</blockquote>" + result[e.offset + e.length:]
    
    # === УРОВЕНЬ 3: ВАЛИДАЦИЯ ===
    validation = validate_formatting(text, entities, result)
    
    if validation['passed']:
        logger.debug("\n✅ Валидация пройдена успешно")
        return result
    else:
        logger.warning("\n⚠️ Валидация не пройдена, запуск ручного форматирования")
        for error in validation['errors']:
            logger.warning(f"  {error}")
        
        # === УРОВЕНЬ 4: РУЧНОЕ ФОРМАТИРОВАНИЕ ===
        manual_result = manual_format(text, entities)
        
        # === УРОВЕНЬ 5: ПОВТОРНАЯ ВАЛИДАЦИЯ ===
        manual_validation = validate_formatting(text, entities, manual_result)
        
        if manual_validation['passed']:
            logger.debug("\n✅ Ручное форматирование успешно")
            return manual_result
        else:
            logger.error("\n❌ КРИТИЧЕСКАЯ ОШИБКА: форматирование не удалось")
            return text  # Возвращаем как есть

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
        
        logger.info(f"📝 Исходный текст: {text[:100]}...")
        
        # Форматируем текст
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
        
        # Форматируем подпись
        if message.caption and message.caption_entities:
            logger.info(f"📝 Форматируем подпись: {text[:100]}...")
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
        "✅ **МНОГОУРОВНЕВЫЙ БОТ**\n\n"
        "📋 **ОСОБЕННОСТИ:**\n"
        "• 🔍 Коррекция entities с учетом эмодзи\n"
        "• ✅ Валидация каждого шага\n"
        "• 🔄 Автокоррекция при ошибках\n"
        "• 📊 Максимальное логирование\n\n"
        "📊 Статистика: /stats\n"
        "✨ Версия: МНОГОУРОВНЕВАЯ"
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
    logger.info("✨✨✨ ЗАПУСК МНОГОУРОВНЕВОГО БОТА ✨✨✨")
    logger.info("✅ Коррекция entities с учетом эмодзи")
    logger.info("✅ Валидация каждого шага")
    logger.info("✅ Автокоррекция при ошибках")
    logger.info("✅ Максимальное логирование")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
