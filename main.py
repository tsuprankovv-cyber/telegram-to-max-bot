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

def create_max_attachments_from_entities(text: str, entities: list) -> list:
    """
    Создает attachment'ы для MAX на основе entities из Telegram
    """
    attachments = []
    
    if not entities:
        return attachments
    
    logger.info(f"🔍 Создание attachment'ов для {len(entities)} entities")
    
    for entity in entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Определяем тип форматирования для MAX
        if entity.type == "bold":
            attachment = {
                "type": "bold",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Жирный: '{entity_text}' (offset: {start}, length: {entity.length})")
            
        elif entity.type == "italic":
            attachment = {
                "type": "italic",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Курсив: '{entity_text}'")
            
        elif entity.type == "underline":
            attachment = {
                "type": "underline",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Подчеркнутый: '{entity_text}'")
            
        elif entity.type == "strikethrough":
            attachment = {
                "type": "strikethrough",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Зачеркнутый: '{entity_text}'")
            
        elif entity.type == "code":
            attachment = {
                "type": "code",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Моноширинный: '{entity_text}'")
            
        elif entity.type == "text_link":
            attachment = {
                "type": "link",
                "payload": {
                    "offset": start,
                    "length": entity.length,
                    "url": entity.url
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Ссылка: '{entity_text}' -> {entity.url}")
            
        elif entity.type == "blockquote":
            attachment = {
                "type": "blockquote",
                "payload": {
                    "offset": start,
                    "length": entity.length
                }
            }
            attachments.append(attachment)
            logger.debug(f"   • Цитата: '{entity_text}'")
    
    return attachments

async def send_to_max_channel(text: str, attachments: list = None):
    """Отправляет сообщение в канал MAX"""
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    message_data = {"text": text}
    if attachments:
        message_data["attachments"] = attachments
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📍 URL: {url}")
    logger.info(f"📝 Текст: {text[:100]}...")
    logger.info(f"📎 Attachments: {json.dumps(attachments, indent=2, ensure_ascii=False) if attachments else 'нет'}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=message_data) as resp:
                response_text = await resp.text()
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО ОТПРАВЛЕНО!")
                    return True
                else:
                    logger.error(f"❌ ОШИБКА MAX: {resp.status}")
                    logger.error(f"📥 Ответ: {response_text}")
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
    
    # Создаем attachment'ы для MAX
    attachments = create_max_attachments_from_entities(text, entities)
    
    # Отправляем в MAX
    success = await send_to_max_channel(text, attachments)
    
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
        "• Жирный\n"
        "• Курсив\n"
        "• Подчеркнутый\n"
        "• Зачеркнутый\n"
        "• Моноширинный\n"
        "• Ссылки\n"
        "• Цитаты"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая отправка"""
    test_text = "Тестовое сообщение с форматированием"
    await send_to_max_channel(test_text)
    await message.answer("✅ Тест отправлен")

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
