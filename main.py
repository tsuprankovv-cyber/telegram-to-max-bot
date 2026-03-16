import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
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

# === ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЗИЦИЯМИ ===

def get_char_width(char: str) -> int:
    """Определяет ширину символа в Telegram (2 для эмодзи, 1 для обычных)"""
    code = ord(char)
    # Эмодзи и спецсимволы
    if 0x1F300 <= code <= 0x1F9FF or 0x2600 <= code <= 0x26FF or 0x2700 <= code <= 0x27BF:
        return 2
    # Специальные типографские символы
    special = {'—': 2, '–': 2, '…': 2, '«': 1, '»': 1, '‑': 1}
    if char in special:
        return special[char]
    # Широкие символы (китайские, японские и т.д.)
    if unicodedata.east_asian_width(char) in ('W', 'F'):
        return 2
    return 1

def build_position_map(text: str) -> Dict[int, int]:
    """
    Строит словарь: для каждой позиции в Python (индекс символа)
    возвращает соответствующую позицию в Telegram (с учётом эмодзи).
    """
    pos_map = {}
    tg_pos = 0
    logger.debug("📊 Построение карты позиций:")
    for py_pos, ch in enumerate(text):
        pos_map[py_pos] = tg_pos
        width = get_char_width(ch)
        if width != 1:
            logger.debug(f"  {py_pos}: '{ch}' -> tg_pos={tg_pos}, ширина={width}")
        tg_pos += width
    pos_map[len(text)] = tg_pos
    logger.debug(f"📊 Всего позиций в Telegram: {tg_pos}, в Python: {len(text)}")
    return pos_map

def correct_entity(entity_start: int, entity_length: int, pos_map: Dict[int, int], text_len: int) -> Tuple[int, int]:
    """
    Преобразует Telegram-позиции в Python-позиции, используя карту.
    Возвращает (start_py, length_py).
    """
    # Находим Python-позицию для начала
    start_py = None
    for py_pos, tg_pos in pos_map.items():
        if py_pos == text_len:
            continue
        if tg_pos >= entity_start:
            start_py = py_pos
            break
    if start_py is None:
        return None, None

    # Определяем конец в Telegram
    tg_end = entity_start + entity_length
    # Находим Python-позицию для конца
    end_py = None
    for py_pos, tg_pos in pos_map.items():
        if tg_pos >= tg_end:
            end_py = py_pos
            break
    if end_py is None:
        end_py = text_len

    length_py = end_py - start_py
    if length_py <= 0:
        return None, None
    return start_py, length_py

# === ФУНКЦИЯ ДЛЯ РАСШИРЕНИЯ ДО ЦЕЛЫХ СЛОВ ===

def expand_to_word(text: str, start: int, end: int) -> Tuple[int, int]:
    """
    Расширяет выделение до границ целого слова
    """
    original_start, original_end = start, end
    
    # Расширяем влево до начала слова
    while start > 0 and (text[start-1].isalnum() or text[start-1] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя-'):
        start -= 1
    
    # Расширяем вправо до конца слова
    while end < len(text) and (text[end].isalnum() or text[end] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя-'):
        end += 1
    
    if start != original_start or end != original_end:
        logger.debug(f"  🔄 Расширение слова: [{original_start}:{original_end}] -> [{start}:{end}]")
        logger.debug(f"     Было: '{text[original_start:original_end]}'")
        logger.debug(f"     Стало: '{text[start:end]}'")
    
    return start, end

# === ФУНКЦИЯ ДЛЯ ПРОВЕРКИ ЦЕЛОСТНОСТИ ТЕКСТА ===

def verify_text_integrity(original: str, formatted: str) -> bool:
    """
    Проверяет, что текст не изменился после форматирования
    """
    clean = re.sub(r'<[^>]+>', '', formatted)
    
    if clean == original:
        logger.debug("✅ Текст не изменился - форматирование корректно")
        return True
    else:
        logger.error("❌ Текст изменился после форматирования!")
        logger.error(f"   Оригинал: {original[:100]}...")
        logger.error(f"   Результат: {clean[:100]}...")
        
        # Поиск первого расхождения
        for i, (oc, cc) in enumerate(zip(original, clean)):
            if oc != cc:
                logger.error(f"   Первое различие на позиции {i}: '{oc}' vs '{cc}'")
                break
        return False

# === ОСНОВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ ===

def format_text(telegram_text: str, entities: list) -> str:
    """
    ВАШ АЛГОРИТМ С ОГРАНИЧЕНИЕМ НА ЦЕЛЫЕ СЛОВА:
    1. Корректируем позиции с учётом эмодзи
    2. Расширяем выделение до целых слов
    3. Получаем правильные фрагменты текста
    4. Находим их в исходном тексте
    5. Применяем форматирование (от конца к началу)
    6. Проверяем целостность
    """
    logger.debug(f"\n{'='*60}")
    logger.debug("🔍 ФОРМАТИРОВАНИЕ С РАСШИРЕНИЕМ ДО СЛОВ")
    logger.debug(f"📝 Исходный текст: {repr(telegram_text[:200])}...")
    
    # ШАГ 1: Строим карту позиций
    pos_map = build_position_map(telegram_text)
    
    # ШАГ 2: Корректируем и расширяем entities
    fragments = []
    logger.debug("\n📋 КОРРЕКЦИЯ И РАСШИРЕНИЕ:")
    
    for i, e in enumerate(entities):
        # Корректируем позиции
        py_start, py_length = correct_entity(e.offset, e.length, pos_map, len(telegram_text))
        if py_start is None:
            logger.warning(f"  ⚠️ Entity {i} не удалось скорректировать, пропускаем")
            continue
        
        # Расширяем до целого слова
        new_start, new_end = expand_to_word(telegram_text, py_start, py_start + py_length)
        fragment = telegram_text[new_start:new_end]
        
        if not fragment:
            logger.warning(f"  ⚠️ Entity {i} дал пустой фрагмент, пропускаем")
            continue
        
        fragments.append({
            'id': i,
            'type': e.type,
            'text': fragment,
            'url': getattr(e, 'url', None),
            'start': new_start,
            'end': new_end
        })
        logger.debug(f"  {i}: {e.type} '{fragment[:50]}...'")
    
    # ШАГ 3: Находим позиции фрагментов в исходном тексте
    positions = []
    logger.debug("\n🔍 ПОИСК ФРАГМЕНТОВ В ТЕКСТЕ:")
    
    for f in fragments:
        # Ищем точное вхождение текста
        pos = telegram_text.find(f['text'])
        if pos == -1:
            logger.error(f"  ❌ Фрагмент '{f['text'][:30]}...' не найден!")
            continue
        
        # Убеждаемся, что это целое слово (проверяем границы)
        word_start = pos
        word_end = pos + len(f['text'])
        
        # Проверяем, что это действительно отдельное слово
        if word_start > 0 and (telegram_text[word_start-1].isalnum() or telegram_text[word_start-1] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя-'):
            logger.warning(f"  ⚠️ Фрагмент не начинается с границы слова, но мы уже расширили")
        
        positions.append({
            'type': f['type'],
            'text': f['text'],
            'url': f['url'],
            'start': word_start,
            'end': word_end
        })
        logger.debug(f"  ✅ Найден '{f['text'][:30]}...' на позиции {word_start}")
    
    if not positions:
        logger.error("❌ Ни одного фрагмента не найдено!")
        return telegram_text
    
    # ШАГ 4: Сортируем от конца к началу
    positions.sort(key=lambda x: -x['start'])
    
    # Применяем форматирование
    result = list(telegram_text)
    offset = 0
    applied = []
    
    logger.debug("\n✏️ ПРИМЕНЕНИЕ ФОРМАТИРОВАНИЯ:")
    
    for p in positions:
        start = p['start'] + offset
        end = p['end'] + offset
        
        # Определяем теги
        if p['type'] == 'bold':
            open_tag, close_tag = '<b>', '</b>'
            logger.debug(f"  🔧 Жирный: '{p['text'][:30]}...'")
        elif p['type'] == 'italic':
            open_tag, close_tag = '<i>', '</i>'
            logger.debug(f"  🔧 Курсив: '{p['text'][:30]}...'")
        elif p['type'] == 'underline':
            open_tag, close_tag = '<u>', '</u>'
        elif p['type'] == 'strikethrough':
            open_tag, close_tag = '<s>', '</s>'
        elif p['type'] == 'code':
            open_tag, close_tag = '<code>', '</code>'
        elif p['type'] == 'pre':
            open_tag, close_tag = '<pre>', '</pre>'
        elif p['type'] == 'blockquote':
            open_tag, close_tag = '<blockquote>', '</blockquote>'
        elif p['type'] == 'text_link':
            link_html = f'<a href="{p["url"]}">{p["text"]}</a>'
            result[start:end] = list(link_html)
            offset += len(link_html) - (end - start)
            applied.append('link')
            logger.debug(f"  🔗 Ссылка: '{p['text'][:30]}...'")
            continue
        else:
            logger.warning(f"  ⏭️ Неподдерживаемый тип: {p['type']}")
            continue
        
        # Вставляем теги
        result[end:end] = list(close_tag)
        result[start:start] = list(open_tag)
        offset += len(open_tag) + len(close_tag)
        applied.append(p['type'])
    
    formatted = ''.join(result)
    
    # ШАГ 5: Проверка целостности
    logger.debug("\n🔍 ПРОВЕРКА ЦЕЛОСТНОСТИ:")
    
    if verify_text_integrity(telegram_text, formatted):
        logger.debug(f"\n✅ УСПЕХ: Применено {len(applied)} форматирований")
        return formatted
    else:
        logger.error("\n❌ ОШИБКА: Текст изменился, возвращаем оригинал")
        return telegram_text

# === КЛАССЫ ДЛЯ РАБОТЫ С МЕДИА (без изменений) ===

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

# === ИНИЦИАЛИЗАЦИЯ ===
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

# === ФУНКЦИИ ОТПРАВКИ ===

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

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

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
        
        # Применяем форматирование с расширением до слов
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
        
        # Применяем форматирование к подписи
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

# === КОМАНДЫ ===

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **БОТ С РАСШИРЕНИЕМ ДО СЛОВ**\n\n"
        "📋 **АЛГОРИТМ:**\n"
        "1. 📄 Берём текст из Telegram\n"
        "2. 🔧 Корректируем позиции с учётом эмодзи\n"
        "3. 🔄 Расширяем выделение до целых слов\n"
        "4. 🔍 Находим фрагменты в тексте\n"
        "5. ✏️ Применяем форматирование\n"
        "6. ✅ Проверяем целостность\n\n"
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

# === ОЧИСТКА ===

async def cleanup():
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()

# === ЗАПУСК ===

async def main():
    logger.info("✨✨✨ ЗАПУСК БОТА С РАСШИРЕНИЕМ ДО СЛОВ ✨✨✨")
    logger.info("✅ Коррекция позиций с учётом эмодзи")
    logger.info("✅ Расширение до целых слов")
    logger.info("✅ Проверка целостности")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
