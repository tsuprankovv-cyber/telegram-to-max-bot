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

# ========== МЕТОД 1: ОПРЕДЕЛЕНИЕ ШИРИНЫ СИМВОЛОВ ==========

def get_char_width(char: str, pos: int = None) -> int:
    """
    Определяет реальную ширину символа в Telegram
    Возвращает 2 для эмодзи и спецсимволов, 1 для обычных
    """
    code = ord(char)
    pos_info = f" на позиции {pos}" if pos is not None else ""
    
    # Вариационные селекторы (не занимают места)
    if 0xFE00 <= code <= 0xFE0F:
        logger.debug(f"    📍 Символ '{char}'{pos_info} - вариационный селектор, ширина 0")
        return 0
    
    # Специальные типографские символы
    special_chars = {
        '—': 2, '–': 2, '…': 2, '«': 1, '»': 1, '‑': 1,
        '−': 2, '×': 2, '÷': 2, '±': 2, '°': 2, '′': 2, '″': 2,
        '€': 2, '£': 2, '¥': 2, '©': 2, '®': 2, '™': 2
    }
    
    if char in special_chars:
        logger.debug(f"    📍 Символ '{char}'{pos_info} - спецсимвол, ширина {special_chars[char]}")
        return special_chars[char]
    
    # Диапазоны эмодзи
    emoji_ranges = [
        (0x1F300, 0x1F9FF), (0x2600, 0x26FF), (0x2700, 0x27BF),
        (0x1F1E6, 0x1F1FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF),
        (0x1F900, 0x1F9FF), (0x1FA70, 0x1FAFF), (0x1F004, 0x1F0CF),
        (0x1F170, 0x1F251), (0x3297, 0x3299), (0x00A9, 0x00AE),
        (0x203C, 0x2049), (0x2122, 0x2139), (0x2194, 0x2199),
        (0x21A9, 0x21AA), (0x231A, 0x231B), (0x23E9, 0x23F3)
    ]
    
    for start, end in emoji_ranges:
        if start <= code <= end:
            logger.debug(f"    📍 Символ '{char}'{pos_info} - эмодзи, ширина 2")
            return 2
    
    # Широкие символы (китайские, японские)
    if unicodedata.east_asian_width(char) in ('W', 'F'):
        logger.debug(f"    📍 Символ '{char}'{pos_info} - широкий символ, ширина 2")
        return 2
    
    logger.debug(f"    📍 Символ '{char}'{pos_info} - обычный символ, ширина 1")
    return 1

# ========== МЕТОД 2: ПОСТРОЕНИЕ КАРТЫ ПОЗИЦИЙ ==========

def build_position_maps(text: str) -> Tuple[Dict[int, int], Dict[int, int]]:
    """
    Строит карты соответствия между Python и Telegram позициями
    Возвращает:
    - py_to_tg: для каждой Python-позиции -> Telegram-позиция
    - tg_to_py: для каждой Telegram-позиции -> Python-позиция
    """
    py_to_tg = {}
    tg_to_py = {}
    tg_pos = 0
    
    logger.debug("\n📊 ПОСТРОЕНИЕ КАРТЫ ПОЗИЦИЙ (посимвольно):")
    logger.debug("-" * 60)
    logger.debug(f"{'Python':<8} {'Char':<10} {'TG start':<10} {'Width':<6}")
    logger.debug("-" * 60)
    
    for py_pos, char in enumerate(text):
        py_to_tg[py_pos] = tg_pos
        tg_to_py[tg_pos] = py_pos
        
        width = get_char_width(char, py_pos)
        logger.debug(f"{py_pos:<8} '{char}' {'':<6} {tg_pos:<10} {width:<6}")
        
        tg_pos += width
    
    # Добавляем конечную позицию
    tg_to_py[tg_pos] = len(text)
    logger.debug(f"{'END':<8} {'':<10} {tg_pos:<10} {'':<6}")
    logger.debug("-" * 60)
    logger.debug(f"📊 ИТОГО: Python позиций: {len(text)}, Telegram позиций: {tg_pos}")
    logger.debug(f"📊 РАЗНИЦА: {tg_pos - len(text)} (из-за эмодзи)")
    
    return py_to_tg, tg_to_py

# ========== МЕТОД 3: КОРРЕКЦИЯ ПОЗИЦИЙ (ИСПРАВЛЕННАЯ) ==========

def correct_entity_position(tg_start: int, tg_length: int, 
                           tg_to_py: Dict[int, int], 
                           text_length: int, entity_index: int) -> Tuple[int, int]:
    """
    Корректирует Telegram позиции в Python позиции
    """
    logger.debug(f"\n  🔄 КОРРЕКЦИЯ ENTITY {entity_index}:")
    logger.debug(f"     Telegram: start={tg_start}, length={tg_length}, end={tg_start+tg_length}")
    
    # Получаем все Telegram позиции и сортируем
    tg_positions = sorted(tg_to_py.keys())
    logger.debug(f"     Доступные Telegram позиции: {tg_positions}")
    
    # Находим Python-позицию для начала - берем точное соответствие
    py_start = None
    for tg_pos in tg_positions:
        if tg_pos == tg_start:
            py_start = tg_to_py[tg_pos]
            logger.debug(f"     Точное совпадение начала: tg_pos={tg_pos} -> py_start={py_start}")
            break
    
    if py_start is None:
        # Если нет точного, берем последнюю позицию ДО
        last_py = 0
        for tg_pos in tg_positions:
            if tg_pos < tg_start:
                last_py = tg_to_py[tg_pos]
                logger.debug(f"     Позиция ДО: tg_pos={tg_pos} -> py_pos={last_py}")
            else:
                break
        py_start = last_py
        logger.debug(f"     Используем последнюю позицию ДО: py_start={py_start}")
    
    # Находим Python-позицию для конца - берем точное соответствие
    tg_end = tg_start + tg_length
    py_end = None
    
    logger.debug(f"     Ищем конец: tg_end={tg_end}")
    for tg_pos in tg_positions:
        if tg_pos == tg_end:
            py_end = tg_to_py[tg_pos]
            logger.debug(f"     Точное совпадение конца: tg_pos={tg_pos} -> py_end={py_end}")
            break
    
    if py_end is None:
        # Если нет точного, берем первую позицию ПОСЛЕ
        for tg_pos in tg_positions:
            if tg_pos > tg_end:
                py_end = tg_to_py[tg_pos]
                logger.debug(f"     Первая позиция ПОСЛЕ: tg_pos={tg_pos} -> py_end={py_end}")
                break
    
    if py_end is None:
        py_end = text_length
        logger.debug(f"     Не найдено, ставим py_end={text_length}")
    
    # Корректируем, чтобы не выходить за границы
    if py_end > text_length:
        py_end = text_length
    
    py_length = py_end - py_start
    logger.debug(f"     РЕЗУЛЬТАТ: Python start={py_start}, length={py_length}, end={py_end}")
    
    return py_start, py_length

# ========== МЕТОД 4: ПРОВЕРКА ФРАГМЕНТА ==========

def analyze_fragment(text: str, start: int, length: int, entity_type: str, index: int):
    """Анализирует фрагмент текста для отладки"""
    end = start + length
    fragment = text[start:end]
    
    logger.debug(f"\n  🔍 АНАЛИЗ ФРАГМЕНТА {index} ({entity_type}):")
    logger.debug(f"     Позиции: [{start}:{end}]")
    logger.debug(f"     Текст: '{fragment}'")
    logger.debug(f"     Длина: {len(fragment)} символов")
    
    # Показываем первые 50 символов с контекстом
    context_start = max(0, start - 20)
    context_end = min(len(text), end + 20)
    context = text[context_start:context_end]
    
    # Добавляем маркеры для наглядности
    marked = (context[:start-context_start] + 
              '【' + fragment[:min(30, len(fragment))] + '】' + 
              context[end-context_start:])
    
    logger.debug(f"     Контекст: ...{marked}...")
    
    # Проверяем начало фрагмента
    if fragment and not fragment[0].isalnum() and fragment[0] not in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя':
        logger.debug(f"     ⚠️ Фрагмент начинается с символа '{fragment[0]}'")
    
    return fragment

# ========== МЕТОД 5: ВАЛИДАЦИЯ ФОРМАТИРОВАНИЯ ==========

def validate_formatting(original_text: str, formatted_text: str, expected_fragments: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Проверяет, что все ожидаемые фрагменты правильно отформатированы
    """
    errors = []
    logger.debug("\n🔍 ВАЛИДАЦИЯ ФОРМАТИРОВАНИЯ:")
    
    # Удаляем все теги для проверки текста
    clean_text = re.sub(r'<[^>]+>', '', formatted_text)
    logger.debug(f"   Очищенный текст: {clean_text[:100]}...")
    
    # Проверяем целостность текста
    if clean_text != original_text:
        errors.append(f"Текст изменился! Длина: {len(clean_text)} vs {len(original_text)}")
        logger.error(f"   ❌ Текст изменился!")
        return False, errors
    
    logger.debug(f"   ✅ Текст не изменился")
    
    # Проверяем каждый фрагмент
    for i, f in enumerate(expected_fragments):
        logger.debug(f"\n   Проверка фрагмента {i} ({f['type']}):")
        logger.debug(f"      Текст: '{f['text'][:50]}...'")
        
        if f['type'] == 'bold':
            pattern = f"<b>{re.escape(f['text'])}</b>"
        elif f['type'] == 'italic':
            pattern = f"<i>{re.escape(f['text'])}</i>"
        elif f['type'] == 'text_link':
            pattern = f'<a href="{f["url"]}">{re.escape(f["text"])}</a>'
        else:
            continue
        
        if re.search(pattern, formatted_text):
            logger.debug(f"      ✅ Найден правильно отформатированным")
        else:
            errors.append(f"Фрагмент '{f['text'][:30]}...' не отформатирован как {f['type']}")
            logger.error(f"      ❌ НЕ НАЙДЕН!")
    
    return len(errors) == 0, errors

# ========== МЕТОД 6: РУЧНОЕ ФОРМАТИРОВАНИЕ ==========

def manual_format(text: str, expected_fragments: List[Dict]) -> str:
    """
    Ручное форматирование с поиском по тексту
    """
    result = text
    logger.debug("\n✋ РУЧНОЕ ФОРМАТИРОВАНИЕ:")
    
    # Сортируем по длине (сначала длинные)
    sorted_fragments = sorted(expected_fragments, key=lambda x: -len(x['text']))
    
    for f in sorted_fragments:
        logger.debug(f"\n   Поиск '{f['text'][:30]}...'")
        pos = result.find(f['text'])
        
        if pos != -1:
            logger.debug(f"      Найдено на позиции {pos}")
            if f['type'] == 'bold':
                result = result[:pos] + f"<b>{f['text']}</b>" + result[pos + len(f['text']):]
                logger.debug(f"      ✅ Применен bold")
            elif f['type'] == 'italic':
                result = result[:pos] + f"<i>{f['text']}</i>" + result[pos + len(f['text']):]
                logger.debug(f"      ✅ Применен italic")
            elif f['type'] == 'text_link':
                result = result[:pos] + f'<a href="{f["url"]}">{f["text"]}</a>' + result[pos + len(f['text']):]
                logger.debug(f"      ✅ Применена ссылка")
        else:
            logger.error(f"      ❌ Не найдено в тексте!")
    
    return result

# ========== ОСНОВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ ==========

def format_text(telegram_text: str, entities: list) -> str:
    """
    КОМБИНИРОВАННЫЙ ПОДХОД С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ
    """
    logger.debug(f"\n{'='*80}")
    logger.debug("🔍 КОМБИНИРОВАННЫЙ ПОДХОД С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ")
    logger.debug(f"📝 Длина текста: {len(telegram_text)} символов")
    logger.debug(f"📝 Первые 200 символов: {repr(telegram_text[:200])}...")
    
    # ШАГ 1: Строим карты позиций
    logger.debug("\n" + "="*60)
    logger.debug("ШАГ 1: ПОСТРОЕНИЕ КАРТЫ ПОЗИЦИЙ")
    py_to_tg, tg_to_py = build_position_maps(telegram_text)
    
    # ШАГ 2: Получаем скорректированные фрагменты
    logger.debug("\n" + "="*60)
    logger.debug("ШАГ 2: ПОЛУЧЕНИЕ ТЕКСТА ИЗ TELEGRAM ПО СКОРРЕКТИРОВАННЫМ ПОЗИЦИЯМ")
    
    fragments = []
    expected_fragments = []
    
    for i, e in enumerate(entities):
        logger.debug(f"\n--- ENTITY {i} ---")
        logger.debug(f"   Тип: {e.type}")
        logger.debug(f"   Telegram offset: {e.offset}")
        logger.debug(f"   Telegram длина: {e.length}")
        if hasattr(e, 'url'):
            logger.debug(f"   URL: {e.url}")
        
        # Корректируем позиции
        py_start, py_length = correct_entity_position(e.offset, e.length, tg_to_py, len(telegram_text), i)
        
        # Получаем текст
        if py_start is not None and py_length > 0:
            fragment = telegram_text[py_start:py_start + py_length]
            
            # Анализируем фрагмент
            analyze_fragment(telegram_text, py_start, py_length, e.type, i)
            
            fragments.append({
                'id': i,
                'type': e.type,
                'text': fragment,
                'url': getattr(e, 'url', None),
                'py_start': py_start,
                'py_length': py_length
            })
            
            expected_fragments.append({
                'type': e.type,
                'text': fragment,
                'url': getattr(e, 'url', None)
            })
        else:
            logger.error(f"   ❌ Не удалось скорректировать позиции для entity {i}")
    
    # ШАГ 3: Ищем фрагменты в болванке
    logger.debug("\n" + "="*60)
    logger.debug("ШАГ 3: ПОИСК ФРАГМЕНТОВ В БОЛВАНКЕ MAX")
    
    max_blank = telegram_text
    positions = []
    
    for i, f in enumerate(fragments):
        logger.debug(f"\n   Поиск фрагмента {i} ({f['type']}):")
        logger.debug(f"      Ищем: '{f['text'][:50]}...'")
        
        pos = max_blank.find(f['text'])
        
        if pos != -1:
            positions.append({
                'type': f['type'],
                'text': f['text'],
                'url': f['url'],
                'start': pos,
                'end': pos + len(f['text'])
            })
            logger.debug(f"      ✅ НАЙДЕН на позиции {pos}")
            
            # Показываем контекст
            context_start = max(0, pos - 20)
            context_end = min(len(max_blank), pos + len(f['text']) + 20)
            context = max_blank[context_start:context_end]
            marked = (context[:pos-context_start] + 
                     '【' + f['text'][:min(30, len(f['text']))] + '】' + 
                     context[pos+len(f['text'])-context_start:])
            logger.debug(f"      Контекст: ...{marked}...")
        else:
            logger.error(f"      ❌ НЕ НАЙДЕН в тексте!")
    
    if not positions:
        logger.error("❌ НИ ОДНОГО ФРАГМЕНТА НЕ НАЙДЕНО!")
        return telegram_text
    
    # ШАГ 4: Применяем форматирование
    logger.debug("\n" + "="*60)
    logger.debug("ШАГ 4: ПРИМЕНЕНИЕ ФОРМАТИРОВАНИЯ")
    
    # Сортируем от конца к началу
    positions.sort(key=lambda x: -x['start'])
    logger.debug(f"   Сортировка от конца к началу: {[p['start'] for p in positions]}")
    
    result = list(max_blank)
    offset = 0
    applied = []
    
    for i, p in enumerate(positions):
        start = p['start'] + offset
        end = p['end'] + offset
        
        logger.debug(f"\n   Применение {i+1}: {p['type']} к '{p['text'][:30]}...'")
        logger.debug(f"      Текущие позиции: start={start}, end={end}")
        logger.debug(f"      Текущий offset: {offset}")
        
        if p['type'] == 'bold':
            # Вставляем теги
            result[end:end] = list('</b>')
            result[start:start] = list('<b>')
            offset += 7
            applied.append('bold')
            logger.debug(f"      ✅ Вставлены теги <b> и </b>, новый offset={offset}")
        elif p['type'] == 'italic':
            result[end:end] = list('</i>')
            result[start:start] = list('<i>')
            offset += 7
            applied.append('italic')
            logger.debug(f"      ✅ Вставлены теги <i> и </i>, новый offset={offset}")
        elif p['type'] == 'text_link':
            link = f'<a href="{p["url"]}">{p["text"]}</a>'
            result[start:end] = list(link)
            offset += len(link) - (end - start)
            applied.append('link')
            logger.debug(f"      ✅ Вставлена ссылка, новый offset={offset}")
        
        # Показываем текущий результат
        current = ''.join(result[max(0, start-50):min(len(result), start+50)])
        logger.debug(f"      Текущий результат: ...{current}...")
    
    formatted = ''.join(result)
    logger.debug(f"\n   ИТОГОВЫЙ ТЕКСТ после форматирования: {formatted[:200]}...")
    logger.debug(f"   Применено форматирований: {len(applied)}")
    
    # ШАГ 5: Валидация
    logger.debug("\n" + "="*60)
    logger.debug("ШАГ 5: ВАЛИДАЦИЯ")
    
    is_valid, errors = validate_formatting(telegram_text, formatted, expected_fragments)
    
    if is_valid:
        logger.debug("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        return formatted
    else:
        logger.warning(f"\n⚠️ ВАЛИДАЦИЯ НЕ ПРОЙДЕНА: {len(errors)} ошибок")
        for e in errors[:3]:
            logger.warning(f"   {e}")
        
        # ШАГ 6: Ручное форматирование
        logger.debug("\n" + "="*60)
        logger.debug("ШАГ 6: РУЧНОЕ ФОРМАТИРОВАНИЕ")
        
        manual_result = manual_format(telegram_text, expected_fragments)
        
        # Проверяем ручной результат
        is_valid, errors = validate_formatting(telegram_text, manual_result, expected_fragments)
        
        if is_valid:
            logger.debug("\n✅ РУЧНОЕ ФОРМАТИРОВАНИЕ УСПЕШНО!")
            return manual_result
        else:
            logger.error("\n❌ ВСЕ МЕТОДЫ НЕ СРАБОТАЛИ!")
            logger.error(f"   Ошибок: {len(errors)}")
            return telegram_text

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
        if message.photo:
            logger.info("🖼️ [ФОТО] Обработка")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1
        
        elif message.video:
            logger.info("🎥 [ВИДЕО] Обработка")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({
                    "type": "video",
                    "payload": {"token": token}
                })
        
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
        
        elif message.voice:
            logger.info("🎤 [ГОЛОСОВОЕ] Обработка")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({
                    "type": "audio",
                    "payload": {"token": token}
                })
        
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
    
    buttons = extract_buttons(message)
    
    if message.text and not message.photo and not message.video and not message.audio and not message.voice and not message.document:
        logger.info("📝 Чисто текстовое сообщение")
        text = message.text
        entities = message.entities or []
        
        logger.info(f"📝 Исходный текст: {text[:100]}...")
        formatted_text = format_text(text, entities)
        logger.info(f"📝 После форматирования: {formatted_text[:100]}...")
        
        attachments = []
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
        
        if message.forward_date and message.forward_from_chat:
            formatted_text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{formatted_text}"
            logger.info(f"🔄 Добавлена подпись о пересылке")
        
        await send_to_max(formatted_text, attachments if attachments else None)
        return
    
    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Медиа сообщение")
        text, attachments = await process_media_message(message)
        
        if not attachments:
            logger.warning("⚠️ Нет вложений")
            return
        
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
            logger.info(f"🔘 Добавлено {len(buttons)} рядов кнопок")
        
        if message.caption and message.caption_entities:
            logger.info(f"📝 Форматируем подпись: {text[:100]}...")
            text = format_text(text, message.caption_entities)
            logger.info(f"📝 После форматирования: {text[:100]}...")
        
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
        "✅ **БОТ С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ**\n\n"
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
    logger.info("✨✨✨ ЗАПУСК БОТА С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ ✨✨✨")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
