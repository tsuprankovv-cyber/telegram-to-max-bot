import os
import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def extract_urls_from_text(text):
    """Извлекает URL из текста (просто для логирования, MAX сам обработает ссылки)"""
    url_pattern = r'https?://[^\s]+'
    return re.findall(url_pattern, text)

async def send_to_max_channel(text: str, photo_url: str = None, telegram_buttons=None):
    """Отправляет сообщение в канал MAX с поддержкой кнопок."""
    url = "https://api.max.ru/v1/messages"
    headers = {
        "Authorization": f"Bearer {MAX_TOKEN}",
        "Content-Type": "application/json"
    }
    
    message_data = {
        "text": text
    }

    # Добавляем медиа, если есть фото
    if photo_url:
        message_data["attachments"] = [
            {
                "type": "image",
                "payload": {
                    "url": photo_url
                }
            }
        ]
    
    # Добавляем кнопки-ссылки из Telegram, если они есть
    if telegram_buttons:
        message_data["attachments"] = message_data.get("attachments", [])
        max_buttons = []
        
        for row in telegram_buttons:
            button_row = []
            for btn in row:
                # Нас интересуют только кнопки с ссылками (url)
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                max_buttons.append(button_row)
        
        if max_buttons:
            message_data["attachments"].append({
                "type": "inline_keyboard",
                "payload": {
                    "buttons": max_buttons
                }
            })
            logging.info(f"Добавлено {len(max_buttons)} рядов кнопок")

    data = {
        "recipient": {
            "chat_id": MAX_CHANNEL_ID
        },
        "message": message_data
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logging.info("✅ Сообщение успешно отправлено в MAX канал")
                    return True
                else:
                    error_text = await resp.text()
                    logging.error(f"❌ Ошибка MAX API: {resp.status} - {error_text}")
                    return False
        except Exception as e:
            logging.error(f"❌ Ошибка при отправке в MAX: {e}")
            return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает ВСЕ сообщения из Telegram-группы в MAX-канал."""
    
    # Проверяем, что сообщение из нужной группы
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        # Логируем информацию об отправителе
        sender_type = "бот" if message.from_user.is_bot else "пользователь"
        logging.info(f"📨 Получено сообщение от {sender_type} @{message.from_user.username or 'без username'}")
        
        # --- 1. Формируем текст сообщения (чистый текст) ---
        text = message.text or message.caption or ''
        
        # Проверяем, есть ли в тексте ссылки (просто для информации)
        urls = extract_urls_from_text(text)
        if urls:
            logging.info(f"🔗 Найдены ссылки в тексте: {urls}")
        
        # --- 2. Обрабатываем фото, если есть ---
        photo_url = None
        if message.photo:
            photo = message.photo[-1]
            file = await telegram_bot.get_file(photo.file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
            logging.info(f"🖼️ Обнаружено фото")

        # --- 3. Извлекаем кнопки-ссылки из сообщения ---
        buttons = None
        if message.reply_markup and message.reply_markup.inline_keyboard:
            logging.info(f"🔘 Обнаружены кнопки в сообщении")
            buttons = message.reply_markup.inline_keyboard

        # --- 4. Отправляем всё в MAX канал ---
        success = await send_to_max_channel(text, photo_url, buttons)
        
        if success:
            logging.info(f"✅ Сообщение успешно переслано в MAX")
        else:
            logging.error(f"❌ Не удалось переслать сообщение")
        
    except Exception as e:
        logging.error(f"❌ Ошибка при обработке сообщения: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен и готов пересылать сообщения с ссылками и кнопками!")

async def main():
    logging.info("🚀 Бот запускается...")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
