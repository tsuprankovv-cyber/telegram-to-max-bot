import os
import asyncio
import logging
import aiohttp
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

def debug_entities(text: str, entities: list, stage: str):
    """Отладочная функция для печати entities"""
    logger.debug(f"🔍 ENTITIES [{stage}]:")
    for i, e in enumerate(entities):
        entity_text = text[e.offset:e.offset + e.length] if e.offset < len(text) else "OUT_OF_RANGE"
        logger.debug(f"   {i}: type={e.type}, offset={e.offset}, len={e.length}, text='{entity_text}'")

def extract_heading_debug(text: str, entities: list) -> tuple[str, str, list, dict]:
    """
    Извлекает заголовок с максимальным логированием
    """
    result = {
        "original_text": text,
        "original_entities_count": len(entities),
        "heading_text": "",
        "remaining_text": "",
        "heading_end_pos": 0,
        "spaces_removed": 0
    }
    
    if not entities:
        logger.debug("📭 Нет entities")
        return "", text, entities, result
    
    # Сортируем entities по позиции
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    debug_entities(text, sorted_entities, "original")
    
    # Проверяем начало
    first = sorted_entities[0]
    if first.offset != 0 or first.type != "bold":
        logger.debug(f"📝 Не заголовок: first offset={first.offset}, type={first.type}")
        return "", text, entities, result
    
    # Собираем жирные подряд
    heading_end = 0
    last_pos = 0
    heading_indices = []
    
    logger.debug("📊 Анализ последовательности жирных:")
    
    for i, e in enumerate(sorted_entities):
        logger.debug(f"   entity {i}: offset={e.offset}, type={e.type}, last_pos={last_pos}")
        
        if e.offset != last_pos:
            logger.debug(f"   → разрыв на entity {i}")
            break
            
        if e.type != "bold":
            logger.debug(f"   → не жирный на entity {i}")
            break
            
        heading_end = e.offset + e.length
        last_pos = heading_end
        heading_indices.append(i)
        logger.debug(f"   → добавили жирный до {heading_end}")
    
    if not heading_indices:
        logger.debug("📝 Нет жирных в начале")
        return "", text, entities, result
    
    # Проверяем текст после
    text_after_raw = text[heading_end:]
    text_after_stripped = text_after_raw.lstrip()
    spaces_removed = len(text_after_raw) - len(text_after_stripped)
    
    result["heading_end_pos"] = heading_end
    result["spaces_removed"] = spaces_removed
    
    logger.debug(f"📏 После жирных: heading_end={heading_end}")
    logger.debug(f"   raw after ({len(text_after_raw)}): '{text_after_raw[:30]}...'")
    logger.debug(f"   stripped ({len(text_after_stripped)}): '{text_after_stripped[:30]}...'")
    logger.debug(f"   удалено пробелов: {spaces_removed}")
    
    if not text_after_stripped:
        logger.debug("📝 Нет текста после жирных")
        return "", text, entities, result
    
    # Формируем результат
    heading_text = text[:heading_end]
    remaining_text = text_after_stripped
    
    # Корректируем оставшиеся entities
    remaining_entities = []
    for i, e in enumerate(sorted_entities):
        if i <= heading_indices[-1]:
            continue
        
        # Смещаем позицию с учетом удаленных пробелов
        new_offset = e.offset - heading_end - spaces_removed
        
        # Создаем копию entity
        new_e = type('Entity', (), {})()
        new_e.offset = new_offset
        new_e.length = e.length
        new_e.type = e.type
        if hasattr(e, 'url'):
            new_e.url = e.url
        
        remaining_entities.append(new_e)
        logger.debug(f"   → entity {i}: offset {e.offset} -> {new_offset}")
    
    result["heading_text"] = heading_text
    result["remaining_text"] = remaining_text
    result["remaining_entities_count"] = len(remaining_entities)
    
    logger.info(f"✅ Заголовок: '{heading_text[:50]}...'")
    debug_entities(remaining_text, remaining_entities, "remaining")
    
    return heading_text, remaining_text, remaining_entities, result

def apply_formatting_debug(text: str, entities: list, stage: str) -> str:
    """
    Применяет форматирование с максимальным логированием
    """
    if not entities:
        return text
    
    logger.debug(f"🎨 ПРИМЕНЕНИЕ ФОРМАТИРОВАНИЯ [{stage}]")
    debug_entities(text, entities, f"before_{stage}")
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    total_shift = 0
    
    for i, e in enumerate(sorted_entities):
        start = e.offset
        end = start + e.length
        entity_text = result[start:end]
        
        logger.debug(f"   обработка {i}: {e.type} '{entity_text}' at {start}")
        
        # Определяем формат
        if e.type == "bold":
            replacement = f"**{entity_text}**"
            shift = 4
        elif e.type == "italic":
            replacement = f"*{entity_text}*"
            shift = 2
        elif e.type == "underline":
            replacement = f"++{entity_text}++"
            shift = 4
        elif e.type == "strikethrough":
            replacement = f"~~{entity_text}~~"
            shift = 4
        elif e.type == "text_link":
            replacement = f"[{entity_text}]({e.url})"
            shift = len(entity_text) + len(e.url) + 4
        elif e.type == "blockquote":
            replacement = f"> {entity_text}"
            shift = 2
        else:
            logger.debug(f"   ⏭️ пропускаем {e.type}")
            continue
        
        # Заменяем
        old_len = len(entity_text)
        new_len = len(replacement)
        result = result[:start] + replacement + result[end:]
        
        # Корректируем позиции следующих entities
        shift_diff = new_len - old_len
        total_shift += shift_diff
        
        logger.debug(f"   ✅ замена: '{entity_text}' -> '{replacement}'")
        logger.debug(f"      old_len={old_len}, new_len={new_len}, shift_diff={shift_diff}, total_shift={total_shift}")
    
    logger.debug(f"📤 РЕЗУЛЬТАТ [{stage}]: {result[:100]}...")
    return result

def process_message_debug(text: str, entities: list) -> str:
    """
    Полная обработка с максимальным логированием
    """
    logger.info("="*80)
    logger.info("🚀 НАЧАЛО ОБРАБОТКИ СООБЩЕНИЯ")
    logger.info(f"📝 Исходный текст: {text[:100]}...")
    logger.info(f"📊 Всего entities: {len(entities)}")
    
    if not text:
        logger.warning("⚠️ Пустой текст")
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
    heading_text, remaining_text, remaining_entities, heading_info = extract_heading_debug(text, entities_copy)
    
    if heading_text:
        logger.info("📌 ОБРАБОТКА С ЗАГОЛОВКОМ")
        logger.info(f"   Заголовок: '{heading_text}'")
        logger.info(f"   Остальной текст: '{remaining_text[:50]}...'")
        logger.info(f"   Entities осталось: {len(remaining_entities)}")
        
        # Формируем заголовок
        heading_markdown = f"# {heading_text}"
        logger.debug(f"   Заголовок markdown: '{heading_markdown}'")
        
        # Обрабатываем остальной текст
        if remaining_text and remaining_entities:
            remaining_markdown = apply_formatting_debug(remaining_text, remaining_entities, "remaining")
            result = f"{heading_markdown}\n\n{remaining_markdown}"
        elif remaining_text:
            result = f"{heading_markdown}\n\n{remaining_text}"
        else:
            result = heading_markdown
        
        logger.info(f"✅ Итоговый текст с заголовком: {result[:100]}...")
        return result
    else:
        logger.info("📝 ОБЫЧНОЕ ФОРМАТИРОВАНИЕ")
        result = apply_formatting_debug(text, entities_copy, "full")
        logger.info(f"✅ Итоговый текст: {result[:100]}...")
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
    
    logger.info("="*80)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📍 URL: {url}")
    logger.info(f"📝 Текст для отправки: {text[:200]}...")
    logger.info(f"📦 Данные запроса: {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=message_data) as resp:
                response_text = await resp.text()
                
                logger.info(f"📥 Статус ответа: {resp.status}")
                logger.info(f"📥 Тело ответа: {response_text}")
                
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
    logger.info(f"👤 От: {message.from_user.full_name}")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    
    # Получаем данные
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    # Обрабатываем
    processed_text = process_message_debug(text, entities.copy())
    
    # Добавляем подпись для пересланных
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        processed_text = f"📢 Переслано из {source}:\n\n{processed_text}"
        logger.info(f"🔄 Добавлена подпись об источнике: {source}")
    
    # Отправляем
    success = await send_to_max_channel(processed_text)
    
    if success:
        logger.info("✅ СООБЩЕНИЕ ПЕРЕСЛАНО")
    else:
        logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
    
    logger.info("="*80)

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
        "• Эмодзи 👋\n\n"
        "Просто отправьте сообщение в группу!"
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
