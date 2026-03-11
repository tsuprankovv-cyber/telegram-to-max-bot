import os
import asyncio
import logging
import aiohttp
import json
import re
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

def normalize_whitespace(text: str) -> str:
    """
    Нормализует пробелы в тексте:
    - Убирает множественные пробелы
    - Оставляет один пробел между словами
    - Сохраняет переносы строк
    """
    # Заменяем множественные пробелы на один
    text = re.sub(r' +', ' ', text)
    # Убираем пробелы в начале строк
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
    # Убираем пробелы в конце строк
    text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)
    return text

def convert_to_markdown(text: str, entities: list) -> str:
    """
    Конвертирует Telegram entities в Markdown для MAX
    """
    if not entities:
        return text
    
    # Сортируем от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    logger.info(f"🔍 Конвертация {len(entities)} entities")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Применяем форматирование
        if entity.type == "bold":
            # Проверяем, является ли этот жирный текст началом всего сообщения
            is_at_start = (start == 0)
            
            # Проверяем, есть ли обычный текст после (игнорируем пробелы)
            text_after = text[end:].lstrip()
            has_text_after = bool(text_after)
            
            # Проверяем, не является ли весь текст жирным
            all_bold = True
            for e in entities:
                if e.type != "bold":
                    all_bold = False
                    break
            
            # Условия для заголовка:
            # 1. Это самый первый элемент И
            # 2. После него есть обычный текст (не считая пробелов) И
            # 3. Не весь текст жирный
            if is_at_start and has_text_after and not all_bold:
                logger.info(f"✅ Заголовок: '{entity_text}'")
                
                # Определяем, сколько пробелов было после жирного текста
                spaces_after = 0
                for char in text[end:]:
                    if char == ' ':
                        spaces_after += 1
                    else:
                        break
                
                # Формируем заголовок с нормализованным пробелом
                heading = f"# {entity_text}"
                
                # Убираем пробелы после жирного текста из результата
                result = result[:start] + heading + result[end + spaces_after:]
                
                # Нормализуем пробелы во всем тексте
                result = normalize_whitespace(result)
                continue
            
            # Обычный жирный текст
            replacement = f"**{entity_text}**"
            logger.debug(f"   • Жирный: '{entity_text}'")
            
        elif entity.type == "italic":
            replacement = f"*{entity_text}*"
            logger.debug(f"   • Курсив: '{entity_text}'")
            
        elif entity.type == "underline":
            replacement = f"++{entity_text}++"
            logger.debug(f"   • Подчеркнутый: '{entity_text}'")
            
        elif entity.type == "strikethrough":
            replacement = f"~~{entity_text}~~"
            logger.debug(f"   • Зачеркнутый: '{entity_text}'")
            
        elif entity.type == "code":
            replacement = f"`{entity_text}`"
            logger.debug(f"   • Моноширинный: '{entity_text}'")
            
        elif entity.type == "pre":
            replacement = f"```\n{entity_text}\n```"
            logger.debug(f"   • Блок кода: '{entity_text}'")
            
        elif entity.type == "text_link":
            replacement = f"[{entity_text}]({entity.url})"
            logger.debug(f"   • Ссылка: '{entity_text}'")
            
        elif entity.type == "blockquote":
            replacement = f"> {entity_text}"
            logger.debug(f"   • Цитата: '{entity_text}'")
            
        else:
            continue
        
        # Заменяем в тексте
        result = result[:start] + replacement + result[end:]
    
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
    
    # Получаем текст и entities
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    logger.info(f"📝 Текст: {text}")
    logger.info(f"📊 Entities: {len(entities)}")
    
    # Конвертируем в Markdown
    markdown_text = convert_to_markdown(text, entities)
    
    # Добавляем подпись для пересланных сообщений
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        markdown_text = f"📢 Переслано из {source}:\n\n{markdown_text}"
        logger.info(f"🔄 Добавлена подпись об источнике: {source}")
    
    # Отправляем в MAX
    success = await send_to_max_channel(markdown_text)
    
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
        "📋 **Поддерживаемое форматирование:**\n"
        "• **Жирный** (**текст**)\n"
        "• *Курсив* (*текст*)\n"
        "• ++Подчеркнутый++ (++текст++)\n"
        "• ~~Зачеркнутый~~ (~~текст~~)\n"
        "• `Моноширинный` (`текст`)\n"
        "• [Ссылки](url) ([текст](url))\n"
        "• > Цитаты (> текст)\n"
        "• # Заголовки (жирный текст в начале)\n"
        "• Эмодзи 👋\n"
        "• Автоматическая нормализация пробелов\n\n"
        "Просто отправьте сообщение с форматированием в группу!"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая отправка"""
    test_text = (
        "**Заголовок теста**   \n\n"
        "Обычный текст с **жирным** и *курсивом*\n\n"
        "++подчеркнутый++ и ~~зачеркнутый~~\n\n"
        "`моноширинный код`\n\n"
        "[ссылка](https://example.com)\n\n"
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
