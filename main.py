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
from typing import List, Tuple, Optional

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

# === УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ОПРЕДЕЛЕНИЯ ШИРИНЫ СИМВОЛА В TELEGRAM ===
def get_telegram_char_width(char: str) -> int:
    """
    Универсально определяет, сколько позиций символ занимает в Telegram.
    Работает для любых эмодзи и спецсимволов автоматически.
    """
    char_code = ord(char)
    
    # Вариационные селекторы (не занимают места, но влияют на отображение)
    if 0xFE00 <= char_code <= 0xFE0F:
        return 0
    
    # Суррогатные пары (в Python это 2 символа, в Telegram - 1)
    if 0xD800 <= char_code <= 0xDFFF:
        return 1
    
    # Проверяем по Unicode-свойствам
    try:
        category = unicodedata.category(char)
        name = unicodedata.name(char, '')
        
        # Эмодзи обычно имеют категорию 'So' (Symbol, other)
        if category == 'So':
            return 2
        
        # Проверяем по ключевым словам в названии
        emoji_keywords = ['EMOJI', 'FACE', 'FLAG', 'HEART', 'HAND', 'CLOCK', 
                         'WEATHER', 'ANIMAL', 'FOOD', 'PLANT', 'SPORT', 'CAR',
                         'HOUSE', 'TOOL', 'NOTE', 'MAIL', 'PHONE', 'COMPUTER']
        
        for keyword in emoji_keywords:
            if keyword in name:
                return 2
    except:
        pass
    
    # Диапазоны эмодзи в Unicode
    emoji_ranges = [
        (0x1F300, 0x1F9FF),  # Различные символы и эмодзи
        (0x2600, 0x26FF),    # Разные символы
        (0x2700, 0x27BF),    # Символы Dingbats
        (0x1F1E6, 0x1F1FF),  # Флаги
        (0x1F600, 0x1F64F),  # Смайлики
        (0x1F680, 0x1F6FF),  # Транспорт
        (0x1F900, 0x1F9FF),  # Дополнительные символы
        (0x1FA70, 0x1FAFF),  # Символы для разных целей
        (0x1F004, 0x1F0CF),  # Игральные карты
        (0x1F170, 0x1F251),  # Дополнительные символы
        (0x3297, 0x3299),    # Японские символы
        (0x00A9, 0x00AE),    # Символы копирайта
        (0x203C, 0x2049),    # Восклицательные знаки
        (0x2122, 0x2139),    # Торговая марка
        (0x2194, 0x2199),    # Стрелки
        (0x21A9, 0x21AA),    # Стрелки возврата
        (0x231A, 0x231B),    # Часы
        (0x2328, 0x23CF),    # Клавиатура и часы
        (0x23E9, 0x23F3),    # Кнопки и часы
        (0x23F8, 0x23FA),    # Кнопки управления
        (0x24C2, 0x25C0),    # Символы
        (0x25B6, 0x25C0),    # Стрелки воспроизведения
        (0x25FB, 0x25FE),    # Квадраты
        (0x2600, 0x2604),    # Погода
        (0x260E, 0x2615),    # Телефон и чай
        (0x2618, 0x261D),    # Листья и палец
        (0x2620, 0x2638),    # Череп и колесо
        (0x2639, 0x263A),    # Смайлики
        (0x2640, 0x2642),    # Мужчина/женщина
        (0x2648, 0x2653),    # Знаки зодиака
        (0x265F, 0x2668),    # Шахматы и кровать
        (0x267B, 0x267F),    # Символ переработки
        (0x2692, 0x2699),    # Инструменты
        (0x269B, 0x269C),    # Символы
        (0x26A0, 0x26A1),    # Предупреждение и молния
        (0x26AA, 0x26AB),    # Круги
        (0x26B0, 0x26B1),    # Гроб и урна
        (0x26BD, 0x26BE),    # Футбол и бейсбол
        (0x26C4, 0x26C5),    # Снеговик и солнце
        (0x26C8, 0x26CE),    # Молния и машина
        (0x26CF, 0x26D4),    # Инструменты и знаки
        (0x26D5, 0x26E9),    # Разное
        (0x26EA, 0x26F5),    # Места и лодка
        (0x26F7, 0x26FA),    # Спорт
        (0x26FD, 0x2705),    # Бутылка и галочка
        (0x2708, 0x270D),    # Самолет и рука
        (0x270F, 0x2712),    # Карандаш
        (0x2714, 0x2716),    # Галочки и кресты
        (0x271D, 0x2721),    # Кресты
        (0x2728, 0x2733),    # Звездочки
        (0x2734, 0x2744),    # Снежинки
        (0x2747, 0x274E),    # Блестки
        (0x2753, 0x2757),    # Вопросы и восклицания
        (0x2763, 0x2764),    # Сердца
        (0x2795, 0x2797),    # Математические знаки
        (0x27A1, 0x27B0),    # Стрелки
        (0x27BF, 0x27BF),    # Стрелка
        (0x2934, 0x2935),    # Стрелки
        (0x2B05, 0x2B07),    # Стрелки
        (0x2B1B, 0x2B1C),    # Квадраты
        (0x2B50, 0x2B55),    # Звезда и круг
        (0x3030, 0x303D),    # Символы
        (0x1F004, 0x1F0CF),  # Маджонг и карты
    ]
    
    for start, end in emoji_ranges:
        if start <= char_code <= end:
            return 2
    
    # Проверяем, является ли символ "широким" в терминах Unicode
    if unicodedata.east_asian_width(char) in ('W', 'F'):
        return 2
    
    # По умолчанию - 1 позиция
    return 1

# === УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОСТРОЕНИЯ КАРТЫ ПОЗИЦИЙ ===
def build_position_map(text: str) -> tuple:
    """
    Строит точную карту соответствия между позициями в Python и Telegram.
    Учитывает все эмодзи и спецсимволы.
    """
    telegram_positions = []  # py_idx -> tg_pos
    python_positions = {}    # tg_pos -> py_idx
    tg_idx = 0
    
    logger.debug("📊 Построение карты позиций:")
    for py_idx, char in enumerate(text):
        telegram_positions.append(tg_idx)
        python_positions[tg_idx] = py_idx
        
        width = get_telegram_char_width(char)
        if width != 1:
            logger.debug(f"  {py_idx}: '{char}' (U+{ord(char):04X}) -> tg_pos={tg_idx}, ширина={width}")
        
        tg_idx += width
    
    # Добавляем конечную позицию
    python_positions[tg_idx] = len(text)
    
    logger.debug(f"📊 Всего позиций в Telegram: {tg_idx}")
    logger.debug(f"📊 Всего символов в Python: {len(text)}")
    logger.debug(f"📊 Разница: {tg_idx - len(text)}")
    
    return telegram_positions, python_positions

# === ФУНКЦИЯ ДЛЯ КОНВЕРТАЦИИ ПОЗИЦИЙ ===
def convert_telegram_to_python(tg_start: int, tg_length: int, 
                               telegram_positions: list, 
                               python_positions: dict,
                               text_length: int) -> tuple:
    """
    Конвертирует диапазон из Telegram-позиций в Python-позиции.
    Точно сохраняет исходные границы выделения.
    """
    tg_end = tg_start + tg_length
    
    # Находим Python-позицию для начала
    py_start = None
    for py_idx, tg_pos in enumerate(telegram_positions):
        if tg_pos >= tg_start:
            py_start = py_idx
            break
    
    if py_start is None:
        return None, None
    
    # Находим Python-позицию для конца
    py_end = None
    
    # Сначала ищем точное совпадение
    if tg_end in python_positions:
        py_end = python_positions[tg_end]
    else:
        # Ищем ближайшую позицию
        for py_idx in range(py_start, len(telegram_positions)):
            if telegram_positions[py_idx] >= tg_end:
                py_end = py_idx
                break
    
    if py_end is None:
        py_end = text_length
    
    # Проверяем корректность
    if py_end <= py_start:
        return None, None
    
    if py_end > text_length:
        py_end = text_length
    
    return py_start, py_end - py_start

# === УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ ===
def format_text(text: str, entities: list) -> str:
    """
    Универсальная функция форматирования с точным учетом позиций.
    Следует исходной разметке Telegram, не расширяет выделения.
    """
    logger.debug(f"\n{'='*60}")
    logger.debug(f"🔍 УНИВЕРСАЛЬНОЕ ФОРМАТИРОВАНИЕ ТЕКСТА")
    logger.debug(f"📝 Исходный текст: {repr(text[:200])}...")
    logger.debug(f"📊 Всего entities: {len(entities)}")
    logger.debug(f"📏 Длина текста: {len(text)} символов (Python)")
    
    if not entities:
        logger.debug("❌ Нет entities для форматирования")
        return text
    
    # Строим карту позиций
    telegram_positions, python_positions = build_position_map(text)
    
    # Статистика по типам
    type_stats = {}
    for e in entities:
        type_stats[e.type] = type_stats.get(e.type, 0) + 1
    logger.debug(f"📊 Типы форматирования: {type_stats}")
    
    # Конвертируем все entities в Python-координаты
    valid_entities = []
    for i, e in enumerate(entities):
        logger.debug(f"\nEntity {i}: {e.type} [Telegram {e.offset}:{e.offset+e.length}]")
        
        py_start, py_length = convert_telegram_to_python(
            e.offset, e.length, 
            telegram_positions, python_positions,
            len(text)
        )
        
        if py_start is None:
            logger.warning(f"  ⚠️ Не удалось конвертировать")
            continue
        
        fragment = text[py_start:py_start+py_length]
        logger.debug(f"  ✅ Конвертировано: [Python {py_start}:{py_start+py_length}] '{fragment}'")
        
        # Проверяем, не на границе ли слова (просто для информации)
        if py_start > 0 and (text[py_start-1].isalnum() or text[py_start-1] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя-'):
            logger.debug(f"  ⚠️ Выделение начинается с середины слова")
        
        if py_start+py_length < len(text) and (text[py_start+py_length].isalnum() or text[py_start+py_length] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя-'):
            logger.debug(f"  ⚠️ Выделение заканчивается на середине слова")
        
        # Создаем объект с Python-координатами
        class FixedEntity:
            pass
        
        fixed_e = FixedEntity()
        fixed_e.type = e.type
        fixed_e.offset = py_start
        fixed_e.length = py_length
        fixed_e.url = getattr(e, 'url', None)
        
        valid_entities.append(fixed_e)
    
    if not valid_entities:
        logger.debug("❌ Нет валидных entities после проверки")
        return text
    
    # ВАЖНО: Сортируем по offset (от меньшего к большему)
    # Это гарантирует правильный порядок обработки
    sorted_entities = sorted(valid_entities, key=lambda e: e.offset)
    logger.debug(f"\n📊 Entities после конвертации и сортировки (по offset):")
    for e in sorted_entities:
        fragment = text[e.offset:e.offset+e.length]
        logger.debug(f"  {e.type} [Python {e.offset}:{e.offset+e.length}] '{fragment[:50]}...'")
    
    # Применяем форматирование
    result = list(text)
    offset_correction = 0
    applied_ranges = []  # Для отслеживания уже примененных диапазонов
    
    for entity in sorted_entities:
        start = entity.offset + offset_correction
        end = start + entity.length
        
        if start >= len(result) or end > len(result):
            logger.warning(f"⚠️ Entity выходит за границы: [{start}:{end}]")
            continue
        
        # Проверяем, не перекрывается ли с уже примененными
        overlap = False
        for ar_start, ar_end in applied_ranges:
            if (start >= ar_start and start < ar_end) or (end > ar_start and end <= ar_end):
                overlap = True
                logger.debug(f"  ⚠️ Перекрывается с диапазоном [{ar_start}:{ar_end}]")
                break
        
        if overlap:
            logger.debug(f"  ⏭️ Пропускаем из-за перекрытия")
            continue
        
        fragment = ''.join(result[start:end])
        
        logger.debug(f"\n--- Entity [{entity.type}] ---")
        logger.debug(f"  📍 Python offset: {entity.offset} -> текущий {start}")
        logger.debug(f"  📏 Длина: {entity.length}")
        logger.debug(f"  📝 Фрагмент: '{fragment}'")
        
        # Определяем HTML-теги
        if entity.type == "bold":
            open_tag, close_tag = '<b>', '</b>'
            logger.debug(f"  🔧 Жирный текст")
        elif entity.type == "italic":
            open_tag, close_tag = '<i>', '</i>'
            logger.debug(f"  🔧 Курсив")
        elif entity.type == "underline":
            open_tag, close_tag = '<u>', '</u>'
        elif entity.type == "strikethrough":
            open_tag, close_tag = '<s>', '</s>'
        elif entity.type == "code":
            open_tag, close_tag = '<code>', '</code>'
        elif entity.type == "pre":
            open_tag, close_tag = '<pre>', '</pre>'
        elif entity.type == "text_link":
            url = entity.url
            link_html = f'<a href="{url}">{fragment}</a>'
            result[start:end] = list(link_html)
            new_end = start + len(link_html)
            applied_ranges.append((start, new_end))
            offset_correction += len(link_html) - (end - start)
            logger.debug(f"  🔗 Ссылка добавлена")
            continue
        elif entity.type == "blockquote":
            open_tag, close_tag = '<blockquote>', '</blockquote>'
        else:
            logger.debug(f"  ⏭️ Пропускаем тип: {entity.type}")
            continue
        
        # Вставляем теги
        result[end:end] = list(close_tag)
        result[start:start] = list(open_tag)
        
        new_end = end + len(open_tag) + len(close_tag)
        applied_ranges.append((start, new_end))
        
        len_diff = len(open_tag) + len(close_tag)
        offset_correction += len_diff
        
        logger.debug(f"  ✅ Применено: {open_tag}{fragment}{close_tag}")
        logger.debug(f"  📊 Новый диапазон: [{start}:{new_end}]")
    
    formatted_text = ''.join(result)
    
    logger.debug(f"\n✅ Итоговый текст: {repr(formatted_text[:200])}...")
    return formatted_text

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
        "format": "html"  # Используем HTML для всех типов форматирования
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
        
        # Форматируем текст с оригинальными позициями
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
        
        # Форматируем подпись с оригинальными позициями
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
        "✅ **УНИВЕРСАЛЬНЫЙ БОТ**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 📝 Текст (жирный, курсив, подчеркнутый, зачеркнутый)\n"
        "• 🔗 Ссылки в тексте\n"
        "• 💬 Цитаты\n"
        "• 🔘 Кнопки-ссылки\n"
        "• 📄 PDF, DOC, XLS (транслит)\n"
        "• 🎥 Видео\n"
        "• 🎵 Аудио (с именами)\n"
        "• 🎤 Голосовые\n"
        "• 🖼️ Фото\n\n"
        "📊 Статистика: /stats\n"
        "✨ Версия: УНИВЕРСАЛЬНАЯ (точный подсчет эмодзи)"
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
    logger.info("✨✨✨ ЗАПУСК УНИВЕРСАЛЬНОГО БОТА ✨✨✨")
    logger.info("✅ Поддержка всех типов форматирования")
    logger.info("✅ АВТОМАТИЧЕСКИЙ УЧЕТ ЭМОДЗИ И СПЕЦСИМВОЛОВ")
    logger.info("✅ ТОЧНОЕ СЛЕДОВАНИЕ ИСХОДНОЙ РАЗМЕТКЕ")
    logger.info("✅ ПРАВИЛЬНАЯ СОРТИРОВКА ПО OFFSET")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
