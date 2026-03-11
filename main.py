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

def extract_heading(text: str, entities: list) -> tuple[str, str, list, int]:
    """
    Извлекает заголовок из начала текста
    Возвращает: (заголовок, остальной_текст, entities_для_остального, смещение)
    """
    if not entities:
        return "", text, [], 0
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    # Проверяем условия для заголовка
    if first.offset != 0 or first.type != "bold":
        return "", text, entities, 0
    
    # Собираем все жирные подряд
    last_pos = 0
    heading_end = 0
    heading_indices = []
    
    for i, e in enumerate(sorted_entities):
        if e.offset != last_pos or e.type != "bold":
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
        heading_indices.append(i)
    
    if not heading_indices:
        return "", text, entities, 0
    
    # Проверяем текст после
    text_after = text[heading_end:]
    stripped = text_after.lstrip()
    spaces = len(text_after) - len(stripped)
    
    if not stripped:
        return "", text, entities, 0
    
    # Заголовок
    heading_text = text[:heading_end]
    
    # Оставшиеся entities с правильным смещением
    remaining = []
    for i, e in enumerate(sorted_entities):
        if i <= heading_indices[-1]:
            continue
        new_e = type('Entity', (), {})()
        new_e.offset = e.offset - heading_end - spaces
        new_e.length = e.length
        new_e.type = e.type
        if hasattr(e, 'url'):
            new_e.url = e.url
        remaining.append(new_e)
    
    logger.info(f"✅ Заголовок: '{heading_text[:30]}...' (пробелов: {spaces})")
    return heading_text, stripped, remaining, spaces

def apply_formatting(text: str, entities: list) -> str:
    """Применяет форматирование к тексту"""
    if not entities:
        return text
    
    # Копируем entities и сортируем с конца
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    shift = 0
    
    for e in sorted_entities:
        start = e.offset
        end = start + e.length
        fragment = result[start:end]
        
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
        
        result = result[:start] + replacement + result[end:]
        shift += len(replacement) - len(fragment)
    
    return result

def process_message_text(text: str, entities: list) -> str:
    """Обрабатывает текст с заголовком и форматированием"""
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
    
    # Извлекаем заголовок
    heading, remaining_text, remaining_entities, spaces = extract_heading(text, entities_copy)
    
    if heading:
        # Заголовок без форматирования (только #)
        heading_md = f"# {heading}"
        
        # Форматируем остальной текст
        if remaining_text:
            remaining_md = apply_formatting(remaining_text, remaining_entities)
            result = f"{heading_md}\n\n{remaining_md}"
        else:
            result = heading_md
        
        return result
    else:
        # Обычное форматирование
        return apply_formatting(text, entities_copy)

async def send_to_max_channel(text: str):
    """Отправляет сообщение в MAX"""
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
    logger.info("📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст: {text[:200]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    logger.error(f"❌ ОШИБКА: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщения в MAX"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО ID: {message.message_id}")
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    processed = process_message_text(text, entities)
    
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        processed = f"📢 Переслано из {source}:\n\n{processed}"
    
    await send_to_max_channel(processed)
    logger.info("="*70)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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
