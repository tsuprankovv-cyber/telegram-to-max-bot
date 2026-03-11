import os
import asyncio
import logging
import aiohttp
import json
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

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

logger.info("="*80)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def convert_telegram_to_max_format(text: str, entities: list) -> str:
    """
    Конвертирует Telegram entities в формат MAX
    MAX использует свой собственный формат разметки
    """
    if not entities:
        return text
    
    # Сортируем entities от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    logger.info(f"🔍 Конвертация {len(entities)} entities в формат MAX")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Конвертируем в формат MAX
        if entity.type == "bold":
            # MAX использует **жирный**
            replacement = f"**{entity_text}**"
            logger.debug(f"   • Жирный: {entity_text} -> **{entity_text}**")
            
        elif entity.type == "italic":
            # MAX использует *курсив*
            replacement = f"*{entity_text}*"
            logger.debug(f"   • Курсив: {entity_text} -> *{entity_text}*")
            
        elif entity.type == "underline":
            # MAX может не поддерживать подчеркивание, используем _подчеркнутый_
            replacement = f"_{entity_text}_"
            logger.debug(f"   • Подчеркнутый: {entity_text} -> _{entity_text}_")
            
        elif entity.type == "strikethrough":
            # MAX может не поддерживать зачеркивание, используем ~зачеркнутый~
            replacement = f"~{entity_text}~"
            logger.debug(f"   • Зачеркнутый: {entity_text} -> ~{entity_text}~")
            
        elif entity.type == "code":
            # MAX использует `моноширинный`
            replacement = f"`{entity_text}`"
            logger.debug(f"   • Моноширинный: {entity_text} -> `{entity_text}`")
            
        elif entity.type == "pre":
            # MAX использует ```блок кода```
            replacement = f"```\n{entity_text}\n```"
            logger.debug(f"   • Блок кода: {entity_text} -> ```...```")
            
        elif entity.type == "text_link":
            # MAX использует [текст](url)
            url = entity.url
            replacement = f"[{entity_text}]({url})"
            logger.debug(f"   • Ссылка: {entity_text} -> [{entity_text}]({url})")
            
        elif entity.type == "text_mention":
            # MAX использует @username или [имя](tg://user?id=id)
            if entity.user.username:
                replacement = f"@{entity.user.username}"
            else:
                replacement = f"[{entity_text}](tg://user?id={entity.user.id})"
            logger.debug(f"   • Упоминание: {entity_text} -> {replacement}")
            
        else:
            logger.warning(f"⚠️ Неподдерживаемый тип: {entity.type}")
            continue
        
        # Заменяем в тексте
        result = result[:start] + replacement + result[end:]
    
    return result

def extract_formatted_text(message: types.Message) -> str:
    """Извлекает текст с конвертацией в формат MAX"""
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    if entities:
        logger.info(f"📝 Обнаружено форматирование ({len(entities)} entities)")
        formatted_text = convert_telegram_to_max_format(text, entities)
        logger.info(f"📤 Текст после конвертации: {formatted_text[:200]}...")
        return formatted_text
    else:
        logger.debug("📝 Обычный текст без форматирования")
        return text

async def send_to_max_with_logging(text: str, test_name: str = ""):
    """Отправка текста с максимальным логированием"""
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # MAX не требует parse_mode, он сам понимает свой формат
    message_data = {"text": text}
    
    logger.info("="*80)
    logger.info(f"🔬 ТЕСТ: {test_name}")
    logger.info(f"📍 URL: {url}")
    logger.info(f"🔑 TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
    logger.info(f"📦 CHAT_ID: {MAX_CHANNEL_ID}")
    logger.info(f"📝 TEXT (MAX формат): {text[:200]}...")
    logger.info(f"📏 TEXT length: {len(text)}")
    logger.info(f"📦 FULL JSON: {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    logger.info("="*80)
    
    try:
        async with aiohttp.ClientSession() as session:
            start_time = asyncio.get_event_loop().time()
            
            async with session.post(url, headers=headers, json=message_data) as resp:
                response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                response_text = await resp.text()
                
                logger.info("="*80)
                logger.info(f"📥 ОТВЕТ MAX API")
                logger.info(f"📊 HTTP STATUS: {resp.status}")
                logger.info(f"⏱ ВРЕМЯ: {response_time:.0f}ms")
                logger.info(f"📋 HEADERS: {dict(resp.headers)}")
                logger.info(f"📦 BODY: {response_text}")
                logger.info("="*80)
                
                if resp.status == 200:
                    logger.info(f"✅ ТЕСТ ПРОЙДЕН: {test_name}")
                    return True, response_text
                else:
                    logger.error(f"❌ ТЕСТ НЕ ПРОЙДЕН: {test_name}")
                    return False, response_text
                    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        logger.exception("ДЕТАЛИ:")
        return False, str(e)

@dp.message()
async def forward_to_max(message: types.Message):
    """Обработчик сообщений с конвертацией в формат MAX"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    
    # Извлекаем текст с конвертацией в формат MAX
    formatted_text = extract_formatted_text(message)
    
    # Добавляем подпись для пересланных сообщений
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
        logger.info(f"🔄 Добавлена подпись об источнике: {source}")
    
    # Отправляем в MAX
    test_name = f"Текст от {message.from_user.full_name}"
    success, response = await send_to_max_with_logging(formatted_text, test_name)
    
    if success:
        logger.info("✅ СООБЩЕНИЕ УСПЕШНО ПЕРЕСЛАНО")
    else:
        logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
    
    logger.info("="*80)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК (ЭТАП 1 - ИСПРАВЛЕННЫЙ)**\n\n"
        "📋 **ТЕСТИРУЕМЫЕ ФОРМАТЫ:**\n"
        "• Жирный текст (**жирный**)\n"
        "• Курсив (*курсив*)\n"
        "• Подчеркнутый (_подчеркнутый_)\n"
        "• Зачеркнутый (~зачеркнутый~)\n"
        "• Моноширинный (`код`)\n"
        "• Ссылки ([текст](url))\n"
        "• Эмодзи\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "🔍 **Логирование включено** — проверяйте логи после каждого теста"
    )

@dp.message(Command("test1"))
async def cmd_test1(message: types.Message):
    """Отправляет тестовый набор для проверки"""
    test_text = (
        "**Жирный текст**\n"
        "*Курсив*\n"
        "_Подчеркнутый_\n"
        "~Зачеркнутый~\n"
        "`Моноширинный`\n"
        "[Ссылка на example](https://example.com)\n"
        "Эмодзи: 👋 🌍 🎉\n"
        "> Цитата\n"
        "***Жирный + Курсив***\n"
        "Обычный текст со **вставкой** форматирования"
    )
    
    await message.answer("🔄 Отправляю тестовый набор в группу...")
    await message.answer(test_text)

async def main():
    logger.info("="*80)
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (ЭТАП 1 - ИСПРАВЛЕННЫЙ)")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info("📋 РЕЖИМ: КОНВЕРТАЦИЯ В ФОРМАТ MAX")
    logger.info("="*80)
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
