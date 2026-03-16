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

def get_char_width(char: str) -> int:
    """
    Определяет реальную ширину символа в Telegram
    Возвращает 2 для эмодзи и спецсимволов, 1 для обычных
    """
    code = ord(char)
    
    # Вариационные селекторы (не занимают места)
    if 0xFE00 <= code <= 0xFE0F:
        return 0
    
    # Специальные типографские символы
    special_chars = {
        '—': 2, '–': 2, '…': 2, '«': 1, '»': 1, '‑': 1,
        '−': 2, '×': 2, '÷': 2, '±': 2, '°': 2, '′': 2, '″': 2,
        '€': 2, '£': 2, '¥': 2, '©': 2, '®': 2, '™': 2
    }
    
    if char in special_chars:
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
            return 2
    
    # Широкие символы (китайские, японские)
    if unicodedata.east_asian_width(char) in ('W', 'F'):
        return 2
    
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
    
    logger.debug("📊 Построение карты позиций:")
    for py_pos, char in enumerate(text):
        py_to_tg[py_pos] = tg_pos
        tg_to_py[tg_pos] = py_pos
        
        width = get_char_width(char)
        if width != 1:
            logger.debug(f"  {py_pos}: '{char}' -> tg_pos={tg_pos}, ширина={width}")
        
        tg_pos += width
    
    # Добавляем конечную позицию
    tg_to_py[tg_pos] = len(text)
    
    logger.debug(f"📊 Всего позиций в Telegram: {tg_pos}")
    logger.debug(f"📊 Всего символов в Python: {len(text)}")
    logger.debug(f"📊 Разница: {tg_pos - len(text)}")
    
    return py_to_tg, tg_to_py

# ========== МЕТОД 3: КОРРЕКЦИЯ ПОЗИЦИЙ ==========

def correct_entity_position(tg_start: int, tg_length: int, 
                           tg_to_py: Dict[int, int], 
                           text_length: int) -> Tuple[int, int]:
    """
    Корректирует Telegram позиции в Python позиции
    Возвращает (py_start, py_length)
    """
    # Находим Python-позицию для начала
    py_start = None
    for tg_pos, py_pos in sorted(tg_to_py.items()):
        if tg_pos >= tg_start:
            py_start = py_pos
            break
    
    if py_start is None:
        return None, None
    
    # Находим Python-позицию для конца
    tg_end = tg_start + tg_length
    py_end = None
    
    for tg_pos, py_pos in sorted(tg_to_py.items()):
        if tg_pos >= tg_end:
            py_end = py_pos
            break
    
    if py_end is None:
        py_end = text_length
    
    if py_end <= py_start:
        return None, None
    
    return py_start, py_end - py_start

# ========== МЕТОД 4: РАСШИРЕНИЕ ДО ГРАНИЦ СЛОВА ==========

def expand_to_word(text: str, start: int, end: int) -> Tuple[int, int]:
    """
    Расширяет выделение до границ слова, но не захватывает соседние слова
    """
    # Сохраняем оригинал для сравнения
    original_start, original_end = start, end
    
    # Русские буквы для проверки
    russian_letters = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    
    # Расширяем влево (только если это часть того же слова)
    while start > 0 and (text[start-1].isalnum() or text[start-1] in russian_letters):
        # Проверяем, не захватываем ли мы чужое слово
        if start < original_start and text[start-1].isspace():
            # Если дошли до пробела - это граница слова
            break
        start -= 1
    
    # Расширяем вправо (только если это часть того же слова)
    while end < len(text) and (text[end].isalnum() or text[end] in russian_letters):
        # Проверяем, не захватываем ли мы чужое слово
        if end > original_end and text[end].isspace():
            # Если дошли до пробела - это граница слова
            break
        end += 1
    
    # Если расширение слишком большое, возвращаем оригинал
    if end - start > original_end - original_start + 20:  # Эмпирическое ограничение
        logger.debug(f"  ⚠️ Слишком большое расширение, возвращаем оригинал")
        return original_start, original_end
    
    if start != original_start or end != original_end:
        logger.debug(f"  🔄 Расширение: [{original_start}:{original_end}] -> [{start}:{end}]")
        logger.debug(f"     Было: '{text[original_start:original_end]}'")
        logger.debug(f"     Стало: '{text[start:end]}'")
    
    return start, end

# ========== МЕТОД 5: ПОИСК ПО КОНТЕКСТУ ==========

def find_with_context(text: str, fragment: str, context_before: str = "", context_after: str = "") -> int:
    """
    Ищет фрагмент с учетом контекста
    """
    # Сначала ищем точное вхождение
    pos = text.find(fragment)
    if pos != -1:
        return pos
    
    # Если не нашли, пробуем найти с контекстом
    if context_before or context_after:
        # Берем кусок текста вокруг фрагмента
        extended = context_before + fragment + context_after
        pos = text.find(extended)
        if pos != -1:
            return pos + len(context_before)
    
    return -1

# ========== МЕТОД 6: ВАЛИДАЦИЯ ФОРМАТИРОВАНИЯ ==========

def validate_formatting(original_text: str, formatted_text: str, expected_fragments: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Проверяет, что все ожидаемые фрагменты правильно отформатированы
    """
    errors = []
    
    # Удаляем все теги для проверки текста
    clean_text = re.sub(r'<[^>]+>', '', formatted_text)
    
    # Проверяем целостность текста
    if clean_text != original_text:
        errors.append(f"Текст изменился! Длина: {len(clean_text)} vs {len(original_text)}")
        return False, errors
    
    # Проверяем каждый фрагмент
    for f in expected_fragments:
        # Ищем открывающий тег
        if f['type'] == 'bold':
            pattern = f"<b>{re.escape(f['text'])}</b>"
        elif f['type'] == 'italic':
            pattern = f"<i>{re.escape(f['text'])}</i>"
        elif f['type'] == 'text_link':
            pattern = f'<a href="{f["url"]}">{re.escape(f["text"])}</a>'
        else:
            continue
        
        if not re.search(pattern, formatted_text):
            errors.append(f"Фрагмент '{f['text'][:30]}...' не отформатирован как {f['type']}")
    
    return len(errors) == 0, errors

# ========== МЕТОД 7: РУЧНОЕ ФОРМАТИРОВАНИЕ ==========

def manual_format(text: str, expected_fragments: List[Dict]) -> str:
    """
    Ручное форматирование с поиском по тексту
    """
    result = text
    
    # Сортируем по длине (сначала длинные)
    sorted_fragments = sorted(expected_fragments, key=lambda x: -len(x['text']))
    
    for f in sorted_fragments:
        # Ищем точное вхождение
        pos = result.find(f['text'])
        if pos != -1:
            if f['type'] == 'bold':
                result = result[:pos] + f"<b>{f['text']}</b>" + result[pos + len(f['text']):]
                logger.debug(f"  ✋ Ручное применение bold для '{f['text'][:30]}...'")
            elif f['type'] == 'italic':
                result = result[:pos] + f"<i>{f['text']}</i>" + result[pos + len(f['text']):]
                logger.debug(f"  ✋ Ручное применение italic для '{f['text'][:30]}...'")
            elif f['type'] == 'text_link':
                result = result[:pos] + f'<a href="{f["url"]}">{f["text"]}</a>' + result[pos + len(f['text']):]
                logger.debug(f"  ✋ Ручное применение link для '{f['text'][:30]}...'")
    
    return result

# ========== ОСНОВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ ==========

def format_text(telegram_text: str, entities: list) -> str:
    """
    КОМБИНИРОВАННЫЙ ПОДХОД:
    
    МЕТОД 1: Карта позиций с учетом эмодзи
    МЕТОД 2: Коррекция координат
    МЕТОД 3: Расширение до слов
    МЕТОД 4: Поиск по контексту
    МЕТОД 5: Валидация результата
    МЕТОД 6: Ручное форматирование при ошибках
    """
    logger.debug(f"\n{'='*60}")
    logger.debug("🔍 КОМБИНИРОВАННЫЙ ПОДХОД")
    logger.debug(f"📝 Текст: {repr(telegram_text[:200])}...")
    
    # ШАГ 1: Строим карты позиций
    py_to_tg, tg_to_py = build_position_maps(telegram_text)
    
    # ШАГ 2: Получаем скорректированные фрагменты
    fragments = []
    expected_fragments = []
    logger.debug("\n📋 СКОРРЕКТИРОВАННЫЕ ФРАГМЕНТЫ:")
    
    for i, e in enumerate(entities):
        # Корректируем позиции
        py_start, py_length = correct_entity_position(e.offset, e.length, tg_to_py, len(telegram_text))
        
        if py_start is None:
            logger.warning(f"  ⚠️ Entity {i} не удалось скорректировать, пробуем оригинал")
            py_start = e.offset
            py_length = min(e.length, len(telegram_text) - e.offset)
        
        # Получаем текст
        fragment = telegram_text[py_start:py_start + py_length]
        
        if not fragment:
            logger.warning(f"  ⚠️ Entity {i} дал пустой фрагмент, пропускаем")
            continue
        
        # Расширяем до слова (но осторожно)
        new_start, new_end = expand_to_word(telegram_text, py_start, py_start + py_length)
        expanded_fragment = telegram_text[new_start:new_end]
        
        # Сохраняем оба варианта
        fragments.append({
            'id': i,
            'type': e.type,
            'text': fragment,
            'expanded_text': expanded_fragment,
            'url': getattr(e, 'url', None),
            'py_start': py_start,
            'py_end': py_start + py_length,
            'expanded_start': new_start,
            'expanded_end': new_end
        })
        
        expected_fragments.append({
            'type': e.type,
            'text': expanded_fragment,  # Используем расширенный для проверки
            'url': getattr(e, 'url', None)
        })
        
        logger.debug(f"  {i}: {e.type}")
        logger.debug(f"     Оригинал: '{fragment[:50]}...'")
        logger.debug(f"     Расширенный: '{expanded_fragment[:50]}...'")
    
    # ШАГ 3: Ищем фрагменты в болванке
    max_blank = telegram_text
    positions = []
    logger.debug("\n🔍 ПОИСК В БОЛВАНКЕ MAX:")
    
    for f in fragments:
        # Сначала пробуем расширенный текст
        pos = max_blank.find(f['expanded_text'])
        text_to_use = f['expanded_text']
        
        if pos == -1:
            # Если не нашли, пробуем оригинальный
            pos = max_blank.find(f['text'])
            text_to_use = f['text']
        
        if pos != -1:
            positions.append({
                'type': f['type'],
                'text': text_to_use,
                'url': f['url'],
                'start': pos,
                'end': pos + len(text_to_use)
            })
            logger.debug(f"  ✅ Найден '{text_to_use[:30]}...' на позиции {pos}")
        else:
            logger.error(f"  ❌ Не найден: '{f['text'][:30]}...'")
    
    if not positions:
        logger.error("❌ Ни одного фрагмента не найдено!")
        return telegram_text
    
    # ШАГ 4: Применяем форматирование
    positions.sort(key=lambda x: -x['start'])
    
    result = list(max_blank)
    offset = 0
    
    logger.debug("\n✏️ ПРИМЕНЕНИЕ ФОРМАТИРОВАНИЯ:")
    
    for p in positions:
        start = p['start'] + offset
        end = p['end'] + offset
        
        if p['type'] == 'bold':
            result[end:end] = list('</b>')
            result[start:start] = list('<b>')
            offset += 7
            logger.debug(f"  🔧 Жирный: '{p['text'][:30]}...'")
        elif p['type'] == 'italic':
            result[end:end] = list('</i>')
            result[start:start] = list('<i>')
            offset += 7
            logger.debug(f"  🔧 Курсив: '{p['text'][:30]}...'")
        elif p['type'] == 'text_link':
            link = f'<a href="{p["url"]}">{p["text"]}</a>'
            result[start:end] = list(link)
            offset += len(link) - (end - start)
            logger.debug(f"  🔗 Ссылка: '{p['text'][:30]}...'")
    
    formatted = ''.join(result)
    
    # ШАГ 5: Валидация
    logger.debug("\n🔍 ВАЛИДАЦИЯ:")
    is_valid, errors = validate_formatting(telegram_text, formatted, expected_fragments)
    
    if is_valid:
        logger.debug("✅ Валидация успешна!")
        return formatted
    else:
        logger.warning(f"⚠️ Валидация не пройдена: {errors}")
        
        # ШАГ 6: Ручное форматирование
        logger.debug("\n✋ РУЧНОЕ ФОРМАТИРОВАНИЕ:")
        manual_result = manual_format(telegram_text, expected_fragments)
        
        # Проверяем ручной результат
        is_valid, errors = validate_formatting(telegram_text, manual_result, expected_fragments)
        
        if is_valid:
            logger.debug("✅ Ручное форматирование успешно!")
            return manual_result
        else:
            logger.error("❌ Все методы не сработали!")
            return telegram_text

# === ОСТАЛЬНЫЕ КЛАССЫ И ФУНКЦИИ (MediaUploader, TelegramDownloader, send_to_max и т.д.) ===
# ... (сохраняем как в предыдущих версиях)

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
    
    # ========== ТЕКСТОВЫЕ СООБЩЕНИЯ ==========
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
    
    # ========== МЕДИА СООБЩЕНИЯ ==========
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
        "✅ **КОМБИНИРОВАННЫЙ БОТ**\n\n"
        "📋 **МЕТОДЫ:**\n"
        "1. 📊 Карта позиций с учетом эмодзи\n"
        "2. 🔧 Коррекция координат\n"
        "3. 🔄 Расширение до слов\n"
        "4. 🔍 Поиск по контексту\n"
        "5. ✅ Валидация результата\n"
        "6. ✋ Ручное форматирование\n\n"
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
    logger.info("✨✨✨ ЗАПУСК КОМБИНИРОВАННОГО БОТА ✨✨✨")
    logger.info("✅ Карта позиций с учетом эмодзи")
    logger.info("✅ Коррекция координат")
    logger.info("✅ Расширение до слов")
    logger.info("✅ Поиск по контексту")
    logger.info("✅ Валидация результата")
    logger.info("✅ Ручное форматирование")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
