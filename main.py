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

def convert_entities_to_markdown(text: str, entities: list) -> str:
    """
    Конвертирует Telegram entities в Markdown для MAX
    """
    if not entities:
        return text
    
    # Сортируем entities от конца к началу
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    result = text
    logger.info(f"🔍 Конвертация {len(entities)} entities в Markdown")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Конвертируем в Markdown для MAX
        if entity.type == "bold":
            replacement = f"**{entity_text}**"
            logger.debug(f"   • Жирный: '{entity_text}' -> **{entity_text}**")
            
        elif entity.type == "italic":
            replacement = f"*{entity_text}*"
            logger.debug(f"   • Курсив: '{entity_text}' -> *{entity_text}*")
            
        elif entity.type == "underline":
            # В Markdown MAX поддерживается ++подчеркнутый++
            replacement = f"++{entity_text}++"
            logger.debug(f"   • Подчеркнутый: '{entity_text}' -> ++{entity_text}++")
            
        elif entity.type == "strikethrough":
            replacement = f"~~{entity_text}~~"
            logger.debug(f"   • Зачеркнутый: '{entity_text}' -> ~~{entity_text}~~")
            
        elif entity.type == "code":
            replacement = f"`{entity_text}`"
            logger.debug(f"   • Моноширинный: '{entity_text}' -> `{entity_text}`")
            
        elif entity.type == "pre":
            replacement = f"```\n{entity_text}\n```"
            logger.debug(f"   • Блок кода: '{entity_text}' -> ```...```")
            
        elif entity.type == "text_link":
            url = entity.url
            replacement = f"[{entity_text}]({url})"
            logger.debug(f"   • Ссылка: '{entity_text}' -> [{entity_text}]({url})")
            
        elif entity.type == "blockquote":
            # В Markdown MAX поддерживается > для цитат
            replacement = f"> {entity_text}"
            logger.debug(f"   • Цитата: '{entity_text}' -> > {entity_text}")
            
        else:
            logger.warning(f"⚠️ Неподдерживаемый тип: {entity.type}")
            continue
        
        # Заменяем в тексте
        result = result[:start] + replacement + result[end:]
    
    logger.info(f"📤 Итоговый Markdown: {result[:200]}...")
    return result

async def send_to_max_channel(text: str):
    """Отправляет сообщение в канал MAX с форматированием Markdown"""
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # КЛЮЧЕВОЙ МОМЕНТ: используем format="markdown" для форматирования
    message_data = {
        "text": text,
        "format": "markdown"  # Этого параметра не было в ваших логах!
    }
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📍 URL: {url}")
    logger.info(f"📝 Текст (Markdown): {text[:100]}...")
    logger.info(f"📦 Полный запрос: {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    
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
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    
    # Получаем текст и entities
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    logger.info(f"📝 Исходный текст: {text}")
    logger.info(f"📊 Entities: {len(entities)}")
    
    # Конвертируем entities в Markdown
    markdown_text = convert_entities_to_markdown(text, entities)
    
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
        "• Жирный (**текст**)\n"
        "• Курсив (*текст*)\n"
        "• Подчеркнутый (++текст++)\n"
        "• Зачеркнутый (~~текст~~)\n"
        "• Моноширинный (`текст`)\n"
        "• Ссылки ([текст](url))\n"
        "• Цитаты (> текст)\n\n"
        "Просто отправьте сообщение с форматированием в группу!"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая отправка с примерами форматирования"""
    test_text = (
        "**жирный текст**\n"
        "*курсив*\n"
        "++подчеркнутый++\n"
        "~~зачеркнутый~~\n"
        "`моноширинный`\n"
        "[ссылка на example](https://example.com)\n"
        "👋 эмодзи\n"
        "> цитата\n"
        "**жирный** и *курсив* вместе"
    )
    await message.answer("🔄 Отправляю тестовое сообщение с форматированием...")
    success = await send_to_max_channel(test_text)
    if success:
        await message.answer("✅ Тест отправлен!")
    else:
        await message.answer("❌ Ошибка")

async def main():
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (С Markdown)")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
