import os
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

async def send_to_max(text: str):
    """Отправляет сообщение в MAX канал"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "recipient": {
            "chat_id": str(MAX_CHANNEL_ID)
        },
        "message": {
            "text": text
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logging.info("✅ Отправлено в MAX")
                    return True
                else:
                    logging.error(f"❌ Ошибка MAX: {resp.status}")
                    return False
        except Exception as e:
            logging.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщение в MAX"""
    
    # Проверяем, что сообщение из нужной группы
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    # ПРАВКА: Убрана проверка на ботов!
    # Теперь пересылаются ВСЕ сообщения
    logging.info(f"📨 Получено от {message.from_user.full_name} (бот: {message.from_user.is_bot})")
    
    text = message.text or message.caption or "Сообщение"
    await send_to_max(text)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен и пересылает сообщения от всех!")

async def main():
    logging.info("🚀 Бот запускается...")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
