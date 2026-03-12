import os
import asyncio
import logging
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

def format_text_with_entities(text: str, entities: list) -> str:
    """Применяет форматирование к тексту"""
    if not entities:
        return text
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        fragment = result[start:end]
        
        logger.debug(f"Форматирование: {entity.type} '{fragment}'")
        
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

def is_heading(text: str, entities: list) -> bool:
    """Проверяет, является ли начало заголовком"""
    if not entities:
        return False
    
    # Сортируем по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    # Если первый элемент не с 0 - перед ним есть обычный текст
    if first.offset != 0:
        logger.debug(f"Не заголовок: первый элемент с позиции {first.offset}")
        return False
    
    # Если первый элемент не жирный
    if first.type != "bold":
        logger.debug(f"Не заголовок: первый элемент {first.type}")
        return False
    
    # Находим конец жирного блока
    last_pos = 0
    last_bold_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        last_bold_end = e.offset + e.length
        last_pos = last_bold_end
    
    if last_bold_end == 0:
        return False
    
    # Проверяем текст после жирного
    text_after = text[last_bold_end:].lstrip()
    
    if not text_after:
        return False
    
    logger.info(f"✅ Заголовок найден")
    return True

def extract_heading_text(text: str, entities: list) -> tuple[str, str, list]:
    """Извлекает заголовок"""
    if not entities:
        return "", text, []
    
    # Сортируем по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    # Находим границу заголовка
    last_pos = 0
    heading_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
    
    if heading_end == 0:
        return "", text, entities
    
    heading = text[:heading_end]
    after_raw = text[heading_end:]
    after_stripped = after_raw.lstrip()
    spaces = len(after_raw) - len(after_stripped)
    
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
    
    logger.info(f"✅ Заголовок: '{heading[:30]}...'")
    return heading, after_stripped, remaining_entities

def process_text_message(text: str, entities: list) -> str:
    """Обработка текстового сообщения"""
    if not text:
        return text
    
    logger.info(f"📝 Обработка текста: {text[:100]}...")
    logger.info(f"📊 Entities: {len(entities)}")
    
    if is_heading(text, entities):
        logger.info("🔍 Обнаружен заголовок")
        heading, rest, rest_entities = extract_heading_text(text, entities)
        heading_formatted = f"# {heading}"
        
        if rest:
            rest_formatted = format_text_with_entities(rest, rest_entities)
            result = f"{heading_formatted}\n\n{rest_formatted}"
            logger.info(f"✅ Текст с заголовком")
            return result
        return heading_formatted
    
    result = format_text_with_entities(text, entities)
    logger.info(f"📝 Обычное форматирование")
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
    logger.info(f"📝 Текст: {text[:200]}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
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
    
    text = message.text or ""
    entities = message.entities or []
    
    processed = process_text_message(text, entities)
    
    if message.forward_date and message.forward_from_chat:
        processed = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{processed}"
    
    await send_to_max(processed)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("✅ Бот работает")

async def main():
    logger.info("🚀 ЗАПУСК")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
