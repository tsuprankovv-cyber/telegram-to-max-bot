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

async def send_to_max(text: str):
    """
    МАКСИМАЛЬНО ПРОСТАЯ отправка сообщения в MAX канал
    """
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Минимальные данные для отправки
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
                logger.info(f"📥 Ответ от MAX: статус {resp.status}, тело: {response_text}")
                
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
        logger.info(f"📨 Получено от {sender.full_name or sender.username} (бот: {sender.is_bot})")
        
        # Берём только текст
        text = message.text or message.caption or "Сообщение без текста"
        
        # Отправляем
        success = await send_to_max(text)
        
        if success:
            logger.info("✅ Сообщение переслано")
        else:
            logger.error("❌ Не удалось переслать")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен в тестовом режиме")

async def main():
    logger.info("🚀 Тестовый бот запускается...")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
