import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from maxapi import Bot as MaxBot

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
max_bot = MaxBot(token=MAX_TOKEN)
dp = Dispatcher()

@dp.message()
async def forward_to_max(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        sender_name = message.from_user.full_name or message.from_user.username or "Пользователь"
        logging.info(f"📨 Получено от: {sender_name} (бот: {message.from_user.is_bot})")
        
        # ПРАВКА 1: Убран префикс, только текст сообщения
        text = message.text or ''  # Теперь без "💬 Имя:"
        
        await max_bot.send_message(
            chat_id=MAX_CHANNEL_ID,
            text=text
        )
        logging.info(f"✅ Сообщение переслано")
        
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен (префикс убран)")

async def main():
    logging.info("🚀 Бот запускается...")
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
