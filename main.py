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

# Инициализация ботов
telegram_bot = Bot(token=TELEGRAM_TOKEN)
max_bot = MaxBot(token=MAX_TOKEN)
dp = Dispatcher()

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает все сообщения из Telegram-группы в MAX-канал"""
    
    # Проверяем, что сообщение из нужной группы
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        # Формируем текст сообщения
        sender_name = message.from_user.full_name or message.from_user.username or "Пользователь"
        text = f"💬 {sender_name}:\n{message.text or ''}"
        
        # Если есть текст
        if message.text:
            await max_bot.send_message(
                chat_id=MAX_CHANNEL_ID,
                text=text
            )
            logging.info(f"Текст переслан от {message.from_user.id}")
        
        # Если есть фото
        elif message.photo:
            photo = message.photo[-1]
            file = await telegram_bot.get_file(photo.file_id)
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
            
            await max_bot.send_photo(
                chat_id=MAX_CHANNEL_ID,
                photo=file_url,
                caption=text
            )
            logging.info(f"Фото переслано от {message.from_user.id}")
        
    except Exception as e:
        logging.error(f"Ошибка при пересылке: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer("✅ Бот запущен и готов пересылать сообщения из группы в MAX!")

async def main():
    """Запуск бота"""
    logging.info("Бот запускается...")
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':

    asyncio.run(main())
