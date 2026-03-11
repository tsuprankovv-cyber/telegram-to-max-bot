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
        logger.debug("📝 Текст не начинается с жирного — обычное форматирование")
        return "", text, entities
    
    # Собираем все жирные фрагменты подряд с начала
    heading_end = 0
    last_pos = 0
    heading_entities = []
    remaining_entities = []
    
    logger.info("🔍 Анализ начала текста на заголовок")
    
    for i, entity in enumerate(sorted_entities):
        if entity.offset != last_pos:
            logger.debug(f"   • Разрыв в позиции {last_pos} -> {entity.offset}")
            remaining_entities = sorted_entities[i:]
            break
            
        if entity.type != "bold":
            logger.debug(f"   • Не жирный тип: {entity.type}")
            remaining_entities = sorted_entities[i:]
            break
            
        heading_end = entity.offset + entity.length
        last_pos = heading_end
        heading_entities.append(entity)
        logger.debug(f"   • Жирный фрагмент: '{text[entity.offset:heading_end]}'")
    else:
        # Все entities обработаны и все были жирными
        remaining_entities = []
    
    # Проверяем, есть ли обычный текст после жирных фрагментов
    text_after = text[heading_end:].lstrip()
    
    if not text_after:
        logger.info("📝 Весь текст жирный — оставляем обычное форматирование")
        return "", text, entities
    
    if not heading_entities:
        return "", text, entities
    
    # Формируем заголовок и оставшийся текст
    heading_text = text[:heading_end].strip()
    remaining_text = text_after
    
    logger.info(f"✅ Обнаружен заголовок: '{heading_text}'")
    logger.info(f"📝 Остальной текст: '{remaining_text[:50]}...'")
    
    return heading_text, remaining_text, remaining_entities

def apply_formatting(text: str, entities: list, offset_shift: int = 0) -> str:
    """
    Применяет форматирование к тексту на основе entities
    """
    if not entities:
        return text
    
    # Корректируем позиции с учетом смещения
    adjusted_entities = []
    for entity in entities:
        entity.offset += offset_shift
        adjusted_entities.append(entity)
    
    # Сортируем от конца к началу
    sorted_entities = sorted(adjusted_entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    logger.debug(f"🔍 Применение форматирования к {len(entities)} entities")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Определяем префикс и суффикс для каждого типа
        if entity.type == "bold":
            prefix, suffix = "**", "**"
        elif entity.type == "italic":
            prefix, suffix = "*", "*"
        elif entity.type == "underline":
            prefix, suffix = "++", "++"
        elif entity.type == "strikethrough":
            prefix, suffix = "~~", "~~"
        elif entity.type == "text_link":
            # Для ссылок особый случай
            replacement = f"[{entity_text}]({entity.url})"
            result = result[:start] + replacement + result[end:]
            continue
        elif entity.type == "blockquote":
            # Для цитат особый случай
            replacement = f"> {entity_text}"
            result = result[:start] + replacement + result[end:]
            continue
        else:
            continue
        
        # Применяем форматирование
        replacement = f"{prefix}{entity_text}{suffix}"
        result = result[:start] + replacement + result[end:]
        logger.debug(f"   • {entity.type}: '{entity_text}'")
    
    return result

def process_message_text(text: str, entities: list) -> str:
    """
    Полная обработка текста с выделением заголовков и форматированием
    """
    if not text:
        return text
    
    # Извлекаем заголовок если есть
    heading_text, remaining_text, remaining_entities = extract_heading(text, entities)
    
    if heading_text:
        # Формируем заголовок, сохраняя все его форматирования
        # Находим все entities, которые относятся к заголовку
        heading_entities = [e for e in entities if e.offset < len(heading_text)]
        
        # Применяем форматирование к заголовку
        formatted_heading = apply_formatting(heading_text, heading_entities, 0)
        
        # Добавляем символ заголовка
        heading_markdown = f"# {formatted_heading}"
        
        # Обрабатываем оставшийся текст
        if remaining_text:
            # Корректируем позиции для оставшихся entities
            heading_len = len(heading_text)
            remaining_markdown = apply_formatting(remaining_text, remaining_entities, -heading_len)
            result = f"{heading_markdown}\n\n{remaining_markdown}"
        else:
            result = heading_markdown
        
        logger.info(f"✅ Итоговый текст с заголовком")
        return result
    else:
        # Обычное форматирование без заголовка
        result = apply_formatting(text, entities, 0)
        logger.info(f"📝 Обычное форматирование")
        return result

async def send_to_max_channel(text: str):
    """Отправляет сообщение в канал MAX с форматированием Markdown"""
    
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
    
    # Получаем текст и entities
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    logger.info(f"📝 Исходный текст: {text}")
    logger.info(f"📊 Entities: {len(entities)}")
    
    # Обрабатываем текст (заголовки + форматирование)
    processed_text = process_message_text(text, entities.copy())
    
    # Добавляем подпись для пересланных сообщений
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        processed_text = f"📢 Переслано из {source}:\n\n{processed_text}"
        logger.info(f"🔄 Добавлена подпись об источнике: {source}")
    
    # Отправляем в MAX
    success = await send_to_max_channel(processed_text)
    
    if success:
        logger.info("✅ СООБЩЕНИЕ ПЕРЕСЛАНО")
    else:
        logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
    
    logger.info("="*70)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК MAX**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📋 **Форматирование:**\n"
        "• **Жирный** → **жирный**\n"
        "• *Курсив* → *курсив*\n"
        "• ++Подчеркнутый++ → ++подчеркнутый++\n"
        "• ~~Зачеркнутый~~ → ~~зачеркнутый~~\n"
        "• [Ссылки](url) → [ссылки](url)\n"
        "• > Цитаты → > цитаты\n"
        "• # Заголовки (жирный текст в начале, с сохранением всех форматов)\n"
        "• Эмодзи 👋\n\n"
        "Просто отправьте сообщение в группу!"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая отправка с примерами сложных заголовков"""
    test_text = (
        "**_жирный курсив_** обычный текст после\n\n"
        "**++жирный подчёркнутый++** и ещё текст\n\n"
        "***жирный курсив*** и дальше\n\n"
        "**обычный жирный** текст\n\n"
        "*просто курсив* не заголовок\n\n"
        "++просто подчёркнутый++ не заголовок\n\n"
        "[ссылка](https://example.com) в тексте\n\n"
        "> цитата\n\n"
        "👋 эмодзи"
    )
    await message.answer("🔄 Отправляю тестовое сообщение...")
    success = await send_to_max_channel(test_text)
    if success:
        await message.answer("✅ Тест отправлен!")
    else:
        await message.answer("❌ Ошибка")

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
