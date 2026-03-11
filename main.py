import os
import asyncio
import logging
import aiohttp
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

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def format_text_with_entities(text: str, entities: list) -> str:
    """
    Применяет форматирование к тексту, проходя по entities от конца к началу
    """
    if not entities:
        return text
    
    # Сортируем от конца к началу, чтобы не сбивать позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        fragment = result[start:end]
        
        # Применяем форматирование
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
        
        # Заменяем
        result = result[:start] + replacement + result[end:]
    
    return result

def is_heading(text: str, entities: list) -> bool:
    """
    Проверяет, является ли начало текста заголовком
    """
    if not entities:
        return False
    
    # Сортируем по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    # Проверяем первый entity
    first = sorted_entities[0]
    if first.offset != 0 or first.type != "bold":
        return False
    
    # Проверяем, что после жирного есть обычный текст
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
    return bool(text_after)

def extract_heading_text(text: str, entities: list) -> tuple[str, str, list]:
    """
    Извлекает заголовок и остальной текст, корректируя entities
    """
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
    
    # Получаем заголовок
    heading = text[:heading_end]
    
    # Текст после заголовка (с сохранением пробелов для правильного подсчета)
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
    
    logger.info(f"✅ Заголовок: '{heading[:30]}...' (пробелов: {spaces})")
    return heading, after_stripped, remaining_entities

def process_message(text: str, entities: list) -> str:
    """
    Полная обработка сообщения
    """
    if not text:
        return text
    
    # Проверяем, является ли начало заголовком
    if is_heading(text, entities):
        # Извлекаем заголовок и остальной текст
        heading, rest, rest_entities = extract_heading_text(text, entities)
        
        # Форматируем заголовок (просто добавляем #, без жирного)
        heading_formatted = f"# {heading}"
        
        # Форматируем остальной текст
        if rest:
            rest_formatted = format_text_with_entities(rest, rest_entities)
            return f"{heading_formatted}\n\n{rest_formatted}"
        return heading_formatted
    
    # Обычное форматирование
    return format_text_with_entities(text, entities)

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
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА")
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
    
    logger.info("="*70)
    logger.info(f"📨 ID: {message.message_id}")
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    processed = process_message(text, entities)
    
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
