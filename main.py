import os
import asyncio
import logging
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

def debug_entities(text: str, entities: list, stage: str):
    """Отладка entities"""
    logger.debug(f"\n{'='*50}")
    logger.debug(f"🔍 ЭТАП: {stage}")
    logger.debug(f"📝 Текст: {repr(text)}")
    logger.debug(f"📊 Всего entities: {len(entities)}")
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    for i, e in enumerate(sorted_entities):
        entity_text = text[e.offset:e.offset + e.length]
        logger.debug(f"  {i}: offset={e.offset}, len={e.length}, type={e.type}, текст='{entity_text}'")
    
    logger.debug(f"{'='*50}\n")

def format_text_with_entities(text: str, entities: list) -> str:
    """Применяет форматирование к тексту"""
    if not entities:
        logger.debug("📭 Нет entities для форматирования")
        return text
    
    debug_entities(text, entities, "ДО форматирования")
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        fragment = result[start:end]
        
        logger.debug(f"🔄 Обработка entity: offset={start}, len={entity.length}, type={entity.type}, текст='{fragment}'")
        
        if entity.type == "bold":
            replacement = f"**{fragment}**"
            logger.debug(f"   → замена на: **{fragment}**")
        elif entity.type == "italic":
            replacement = f"*{fragment}*"
            logger.debug(f"   → замена на: *{fragment}*")
        elif entity.type == "underline":
            replacement = f"++{fragment}++"
            logger.debug(f"   → замена на: ++{fragment}++")
        elif entity.type == "strikethrough":
            replacement = f"~~{fragment}~~"
            logger.debug(f"   → замена на: ~~{fragment}~~")
        elif entity.type == "text_link":
            replacement = f"[{fragment}]({entity.url})"
            logger.debug(f"   → замена на: [{fragment}]({entity.url})")
        elif entity.type == "blockquote":
            replacement = f"> {fragment}"
            logger.debug(f"   → замена на: > {fragment}")
        else:
            logger.debug(f"   → пропуск (неподдерживаемый тип)")
            continue
        
        result = result[:start] + replacement + result[end:]
        logger.debug(f"   ✅ Текст после замены: {repr(result)}")
    
    logger.debug(f"📤 РЕЗУЛЬТАТ: {repr(result)}")
    return result

def is_heading(text: str, entities: list) -> bool:
    """Проверяет, является ли начало заголовком"""
    logger.debug(f"\n{'='*50}")
    logger.debug(f"🔍 ПРОВЕРКА ЗАГОЛОВКА")
    logger.debug(f"📝 Текст: {repr(text[:50])}...")
    
    if not entities:
        logger.debug("❌ Нет entities")
        return False
    
    # Сортируем по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    logger.debug(f"📌 Первый entity: offset={first.offset}, type={first.type}")
    
    # Если первый entity не с 0 - перед ним есть обычный текст
    if first.offset != 0:
        logger.debug(f"❌ Не заголовок: первый элемент не в начале (offset={first.offset})")
        return False
    
    # Если первый элемент не жирный
    if first.type != "bold":
        logger.debug(f"❌ Не заголовок: первый элемент не жирный ({first.type})")
        return False
    
    # Находим конец жирного блока
    last_pos = 0
    last_bold_end = 0
    
    logger.debug("📊 Анализ последовательности:")
    for i, e in enumerate(sorted_entities):
        logger.debug(f"  {i}: offset={e.offset}, type={e.type}, ожидаемая позиция={last_pos}")
        
        if e.offset != last_pos:
            logger.debug(f"  ❌ Разрыв на позиции {e.offset}")
            break
        if e.type != "bold":
            logger.debug(f"  ❌ Не жирный тип")
            break
        
        last_bold_end = e.offset + e.length
        last_pos = last_bold_end
        logger.debug(f"  ✅ Добавлен жирный, конец блока={last_bold_end}")
    
    if last_bold_end == 0:
        logger.debug("❌ Не найден конец жирного блока")
        return False
    
    # Проверяем текст после жирного
    text_after = text[last_bold_end:].lstrip()
    logger.debug(f"📝 Текст после жирного: '{text_after[:50]}...'")
    
    if not text_after:
        logger.debug("❌ Нет текста после жирного")
        return False
    
    logger.debug(f"✅ ЭТО ЗАГОЛОВОК!")
    logger.debug(f"{'='*50}\n")
    return True

def extract_heading_text(text: str, entities: list) -> tuple[str, str, list]:
    """Извлекает заголовок"""
    logger.debug(f"\n{'='*50}")
    logger.debug(f"🔍 ИЗВЛЕЧЕНИЕ ЗАГОЛОВКА")
    
    if not entities:
        logger.debug("❌ Нет entities")
        return "", text, []
    
    # Сортируем по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    # Находим границу заголовка
    last_pos = 0
    heading_end = 0
    
    for e in sorted_entities:
        logger.debug(f"  entity: offset={e.offset}, type={e.type}, last_pos={last_pos}")
        if e.offset != last_pos:
            logger.debug(f"  ❌ Разрыв на {e.offset}")
            break
        if e.type != "bold":
            logger.debug(f"  ❌ Не жирный тип")
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
        logger.debug(f"  ✅ Добавлен, конец={heading_end}")
    
    if heading_end == 0:
        logger.debug("❌ Не найден конец заголовка")
        return "", text, entities
    
    heading = text[:heading_end]
    after_raw = text[heading_end:]
    after_stripped = after_raw.lstrip()
    spaces = len(after_raw) - len(after_stripped)
    
    logger.debug(f"📌 Заголовок: '{heading}'")
    logger.debug(f"📌 Пробелов после: {spaces}")
    logger.debug(f"📌 Остальной текст: '{after_stripped[:50]}...'")
    
    # Корректируем entities для остального текста
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
            logger.debug(f"  entity {e.offset} -> {new_e.offset}")
    
    logger.debug(f"{'='*50}\n")
    return heading, after_stripped, remaining_entities

def process_text_message(text: str, entities: list) -> str:
    """Полная обработка текста"""
    logger.info(f"\n{'='*80}")
    logger.info(f"📝 ОБРАБОТКА ТЕКСТА")
    logger.info(f"Исходный текст: {repr(text)}")
    logger.info(f"Количество entities: {len(entities)}")
    
    if is_heading(text, entities):
        logger.info("✅ ОБНАРУЖЕН ЗАГОЛОВОК")
        heading, rest, rest_entities = extract_heading_text(text, entities)
        
        heading_formatted = f"# {heading}"
        logger.info(f"Заголовок после форматирования: {repr(heading_formatted)}")
        
        if rest:
            logger.info(f"Остальной текст (до форматирования): {repr(rest)}")
            rest_formatted = format_text_with_entities(rest, rest_entities)
            result = f"{heading_formatted}\n\n{rest_formatted}"
            logger.info(f"Итоговый текст: {repr(result)}")
            return result
        
        logger.info(f"Итоговый текст (только заголовок): {repr(heading_formatted)}")
        return heading_formatted
    
    logger.info("📝 ОБЫЧНОЕ ФОРМАТИРОВАНИЕ")
    result = format_text_with_entities(text, entities)
    logger.info(f"Итоговый текст: {repr(result)}")
    return result

async def send_to_max(text: str):
    """Отправка в MAX"""
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "format": "markdown"
    }
    
    logger.info("="*80)
    logger.info("📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст для отправки: {text[:200]}...")
    logger.debug(f"📦 Данные: {json.dumps(data, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            response_text = await resp.text()
            logger.info(f"📥 Статус: {resp.status}")
            logger.debug(f"📥 Ответ: {response_text}")
            
            if resp.status == 200:
                logger.info("✅ УСПЕШНО")
                return True
            logger.error(f"❌ Ошибка {resp.status}")
            return False

@dp.message()
async def forward(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    if message.text:
        text = message.text or ""
        entities = message.entities or []
        
        processed_text = process_text_message(text, entities)
        
        if message.forward_date and message.forward_from_chat:
            source = message.forward_from_chat.title
            processed_text = f"📢 Переслано из {source}:\n\n{processed_text}"
        
        await send_to_max(processed_text)
        return
    
    logger.warning(f"⚠️ Неподдерживаемый тип: {message.content_type}")

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("✅ Текстовый бот с максимальными логами")

async def main():
    logger.info("🚀 ЗАПУСК ТЕКСТОВОГО БОТА С ЛОГАМИ")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
