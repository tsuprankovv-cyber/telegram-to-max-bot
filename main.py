import os
import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

async def send_to_max_channel(text: str):
    """Отправляет сообщение в канал MAX через прямой HTTP-запрос"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Правильный формат: chat_id как строка
    data = {
        "recipient": {
            "chat_id": str(MAX_CHANNEL_ID)
        },
        "message": {
            "text": text
        }
    }
    
    logger.info(f"📤 Отправка в MAX: {json.dumps(data)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                logger.info(f"📥 Ответ MAX: {resp.status} - {response_text}")
                
                if resp.status == 200:
                    logger.info("✅ Успешно отправлено")
                    return True
                else:
                    logger.error(f"❌ Ошибка: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка соединения: {e}")
            return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщение в MAX"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        sender = message.from_user
        logger.info(f"📨 Получено от {sender.full_name or sender.username}")
        
        # Берём текст сообщения
        text = message.text or message.caption or "Сообщение"
        
        # Отправляем в MAX
        success = await send_to_max_channel(text)
        
        if success:
            logger.info("✅ Сообщение переслано")
        else:
            logger.error("❌ Не удалось переслать")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен и готов пересылать сообщения!")

async def main():
    logger.info("🚀 Бот запускается...")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
