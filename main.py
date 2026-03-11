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

def extract_heading(text: str, entities: list) -> tuple[str, str, list]:
    """
    Извлекает заголовок из начала текста
    """
    if not entities:
        return "", text, []
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    # Проверяем начало
    if first.offset != 0 or first.type != "bold":
        return "", text, entities
    
    # Собираем все жирные подряд
    last_pos = 0
    heading_end = 0
    heading_indices = []
    
    for i, e in enumerate(sorted_entities):
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
        heading_indices.append(i)
    
    if not heading_indices:
        return "", text, entities
    
    # Получаем текст после заголовка и считаем пробелы
    after_text = text[heading_end:]
    stripped = after_text.lstrip()
    spaces_count = len(after_text) - len(stripped)
    
    if not stripped:
        return "", text, entities
    
    # Заголовок
    heading = text[:heading_end]
    
    # Смещение для оставшихся entities: длина заголовка + пробелы
    shift = heading_end + spaces_count
    
    # Корректируем оставшиеся entities
    remaining = []
    for i, e in enumerate(sorted_entities):
        if i <= heading_indices[-1]:
            continue
        
        # Создаем копию с новым смещением
        new_e = type('Entity', (), {})()
        new_e.offset = e.offset - shift
        new_e.length = e.length
        new_e.type = e.type
        if hasattr(e, 'url'):
            new_e.url = e.url
        remaining.append(new_e)
    
    logger.info(f"✅ Заголовок: '{heading[:30]}...' (пробелов: {spaces_count})")
    return heading, stripped, remaining

def apply_formatting(text: str, entities: list) -> str:
    """
    Применяет форматирование с учетом динамического смещения
    """
    if not entities:
        return text
    
    # Сортируем с конца
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    total_shift = 0
    
    for e in sorted_entities:
        # Корректируем позицию с учетом предыдущих замен
        pos = e.offset + total_shift
        end = pos + e.length
        fragment = result[pos:end]
        
        # Определяем замену
        if e.type == "bold":
            replacement = f"**{fragment}**"
        elif e.type == "italic":
            replacement = f"*{fragment}*"
        elif e.type == "underline":
            replacement = f"++{fragment}++"
        elif e.type == "strikethrough":
            replacement = f"~~{fragment}~~"
        elif e.type == "text_link":
            replacement = f"[{fragment}]({e.url})"
        elif e.type == "blockquote":
            replacement = f"> {fragment}"
        else:
            continue
        
        # Заменяем и обновляем смещение
        result = result[:pos] + replacement + result[end:]
        total_shift += len(replacement) - len(fragment)
    
    return result

def process_message(text: str, entities: list) -> str:
    """
    Полная обработка сообщения
    """
    if not text:
        return text
    
    # Копируем entities
    entities_copy = []
    for e in entities:
        new_e = type('Entity', (), {})()
        new_e.offset = e.offset
        new_e.length = e.length
        new_e.type = e.type
        if hasattr(e, 'url'):
            new_e.url = e.url
        entities_copy.append(new_e)
    
    # Проверяем заголовок
    heading, rest, rest_entities = extract_heading(text, entities_copy)
    
    if heading:
        # Заголовок
        heading_md = f"# {heading}"
        
        # Остальной текст
        if rest:
            rest_md = apply_formatting(rest, rest_entities)
            return f"{heading_md}\n\n{rest_md}"
        return heading_md
    
    # Обычное форматирование
    return apply_formatting(text, entities_copy)

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
