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

# Проверка наличия всех переменных
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

def extract_heading(text: str, entities: list) -> tuple[str, str, list]:
    """
    Извлекает заголовок из начала текста если:
    - Текст начинается с жирных слов
    - Жирные слова идут подряд
    - После них есть обычный текст
    - Это не весь текст
    """
    if not entities:
        return "", text, entities
    
    # Сортируем entities по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    # Проверяем, начинается ли текст с жирного
    first_entity = sorted_entities[0]
    if first_entity.offset != 0 or first_entity.type != "bold":
        return "", text, entities
    
    # Собираем все жирные фрагменты подряд с начала
    heading_end = 0
    last_pos = 0
    heading_indices = []
    
    for i, entity in enumerate(sorted_entities):
        if entity.offset != last_pos:
            break
            
        if entity.type != "bold":
            break
            
        heading_end = entity.offset + entity.length
        last_pos = heading_end
        heading_indices.append(i)
    
    if not heading_indices:
        return "", text, entities
    
    # Проверяем, есть ли обычный текст после жирных фрагментов
    # Сохраняем информацию о пробелах!
    text_after = text[heading_end:]
    text_after_stripped = text_after.lstrip()
    spaces_count = len(text_after) - len(text_after_stripped)
    
    if not text_after_stripped:
        return "", text, entities
    
    # Формируем заголовок и оставшийся текст
    heading_text = text[:heading_end]
    remaining_text = text_after_stripped
    
    # Создаем копии оставшихся entities с правильным смещением
    remaining_entities = []
    for i, entity in enumerate(sorted_entities):
        if i <= heading_indices[-1]:
            continue
        
        # Смещаем позицию с учетом длины заголовка И удаленных пробелов
        new_entity = type('Entity', (), {})()
        new_entity.offset = entity.offset - heading_end - spaces_count
        new_entity.length = entity.length
        new_entity.type = entity.type
        if hasattr(entity, 'url'):
            new_entity.url = entity.url
        remaining_entities.append(new_entity)
    
    logger.info(f"✅ Заголовок: '{heading_text[:30]}...' (пробелов после: {spaces_count})")
    
    return heading_text, remaining_text, remaining_entities

def apply_formatting(text: str, entities: list) -> str:
    """
    Применяет форматирование к тексту с учетом смещения
    """
    if not entities:
        return text
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    offset_correction = 0
    
    for entity in sorted_entities:
        # Корректируем позицию с учетом предыдущих замен
        start = entity.offset + offset_correction
        end = start + entity.length
        entity_text = result[start:end]
        
        # Применяем форматирование
        if entity.type == "bold":
            replacement = f"**{entity_text}**"
            format_length = 4
        elif entity.type == "italic":
            replacement = f"*{entity_text}*"
            format_length = 2
        elif entity.type == "underline":
            replacement = f"++{entity_text}++"
            format_length = 4
        elif entity.type == "strikethrough":
            replacement = f"~~{entity_text}~~"
            format_length = 4
        elif entity.type == "text_link":
            replacement = f"[{entity_text}]({entity.url})"
            format_length = len(entity_text) + len(entity.url) + 4
        elif entity.type == "blockquote":
            replacement = f"> {entity_text}"
            format_length = 2
        else:
            continue
        
        # Заменяем в тексте
        result = result[:start] + replacement + result[end:]
        
        # Корректируем смещение для следующих entities
        offset_correction += len(replacement) - len(entity_text)
    
    return result

def process_message_text(text: str, entities: list) -> str:
    """
    Полная обработка текста с заголовками и форматированием
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
    
    # Извлекаем заголовок
    heading_text, remaining_text, remaining_entities = extract_heading(text, entities_copy)
    
    if heading_text:
        # Заголовок (без дополнительного форматирования жирным, только #)
        heading_markdown = f"# {heading_text}"
        
        # Обрабатываем остальной текст
        if remaining_text:
            remaining_markdown = apply_formatting(remaining_text, remaining_entities)
            result = f"{heading_markdown}\n\n{remaining_markdown}"
        else:
            result = heading_markdown
        
        return result
    else:
        # Обычное форматирование
        return apply_formatting(text, entities_copy)

async def send_to_max_channel(text: str):
    """Отправляет сообщение в канал MAX"""
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    message_data = {
        "text": text,
        "format": "markdown"
    }
    
    logger.info("="*80)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📝 Текст: {text[:200]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=message_data) as resp:
                response_text = await resp.text()
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО ОТПРАВЛЕНО!")
                    return True
                else:
                    logger.error(f"❌ ОШИБКА MAX: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщения из Telegram в MAX"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    # Обрабатываем текст
    processed_text = process_message_text(text, entities)
    
    # Добавляем подпись для пересланных
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        processed_text = f"📢 Переслано из {source}:\n\n{processed_text}"
    
    # Отправляем
    await send_to_max_channel(processed_text)
    
    logger.info("="*80)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК MAX**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`"
    )

async def main():
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
