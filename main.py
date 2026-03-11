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

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def apply_formatting_safe(text: str, entities: list) -> str:
    """
    Безопасно применяет форматирование к тексту
    без дублирования символов
    """
    if not entities:
        return text
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    logger.debug(f"🔍 Применение форматирования к {len(entities)} entities")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Определяем символы форматирования
        if entity.type == "bold":
            formatted = f"**{entity_text}**"
        elif entity.type == "italic":
            formatted = f"*{entity_text}*"
        elif entity.type == "underline":
            formatted = f"++{entity_text}++"
        elif entity.type == "strikethrough":
            formatted = f"~~{entity_text}~~"
        elif entity.type == "text_link":
            formatted = f"[{entity_text}]({entity.url})"
        elif entity.type == "blockquote":
            formatted = f"> {entity_text}"
        else:
            continue
        
        # Заменяем в тексте
        result = result[:start] + formatted + result[end:]
        logger.debug(f"   • {entity.type}: '{entity_text}' -> '{formatted}'")
    
    return result

def extract_heading_safe(text: str, entities: list) -> tuple[str, list, list]:
    """
    Безопасно извлекает заголовок, не изменяя entities
    """
    if not entities:
        return "", text, entities
    
    # Находим первый entity
    first_entity = entities[0]
    
    # Проверяем условия для заголовка
    if first_entity.offset != 0 or first_entity.type != "bold":
        return "", text, entities
    
    # Собираем все жирные подряд с начала
    heading_end = 0
    last_pos = 0
    heading_entities = []
    remaining_entities = []
    
    for entity in entities:
        if entity.offset != last_pos:
            remaining_entities = [e for e in entities if e.offset >= entity.offset]
            break
        
        if entity.type != "bold":
            remaining_entities = [e for e in entities if e.offset >= entity.offset]
            break
        
        heading_end = entity.offset + entity.length
        last_pos = heading_end
        heading_entities.append(entity)
    else:
        # Все entities жирные
        remaining_entities = []
    
    # Проверяем, есть ли обычный текст после
    text_after = text[heading_end:].lstrip()
    if not text_after:
        return "", text, entities
    
    if not heading_entities:
        return "", text, entities
    
    # Формируем заголовок и оставшийся текст
    heading_text = text[:heading_end]
    remaining_text = text_after
    
    # Корректируем позиции для оставшихся entities
    shift = heading_end
    for entity in remaining_entities:
        entity.offset -= shift
    
    logger.info(f"✅ Заголовок: '{heading_text[:30]}...'")
    
    return heading_text, remaining_text, remaining_entities

def process_message_text(text: str, entities: list) -> str:
    """
    Обрабатывает текст с заголовками и форматированием
    """
    if not text:
        return text
    
    # Копируем entities чтобы не изменять оригинал
    entities_copy = []
    for e in entities:
        # Создаем копию entity
        class EntityCopy:
            def __init__(self, entity):
                self.offset = entity.offset
                self.length = entity.length
                self.type = entity.type
                if hasattr(entity, 'url'):
                    self.url = entity.url
        entities_copy.append(EntityCopy(e))
    
    # Извлекаем заголовок
    heading_text, remaining_text, remaining_entities = extract_heading_safe(text, entities_copy)
    
    if heading_text:
        # Применяем форматирование к заголовку
        heading_entities = [e for e in entities_copy if e.offset < len(heading_text)]
        formatted_heading = apply_formatting_safe(heading_text, heading_entities)
        
        # Формируем результат
        if remaining_text:
            formatted_remaining = apply_formatting_safe(remaining_text, remaining_entities)
            result = f"# {formatted_heading}\n\n{formatted_remaining}"
        else:
            result = f"# {formatted_heading}"
        
        logger.info("✅ Текст с заголовком")
        return result
    else:
        # Обычное форматирование
        result = apply_formatting_safe(text, entities_copy)
        logger.info("📝 Обычное форматирование")
        return result

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
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📍 URL: {url}")
    logger.info(f"📝 Текст: {text[:100]}...")
    
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
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    logger.info(f"📝 Текст: {text[:100]}...")
    logger.info(f"📊 Entities: {len(entities)}")
    
    # Обрабатываем текст
    processed_text = process_message_text(text, entities)
    
    # Добавляем подпись для пересланных
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        processed_text = f"📢 Переслано из {source}:\n\n{processed_text}"
    
    # Отправляем
    await send_to_max_channel(processed_text)
    
    logger.info("="*70)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК MAX**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📋 **Форматирование:**\n"
        "• **Жирный**\n"
        "• *Курсив*\n"
        "• ++Подчеркнутый++\n"
        "• ~~Зачеркнутый~~\n"
        "• [Ссылки](url)\n"
        "• > Цитаты\n"
        "• # Заголовки\n"
        "• Эмодзи 👋"
    )

async def main():
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
