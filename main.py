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

async def download_file(file_id: str) -> str:
    """Скачивает файл из Telegram и возвращает ссылку на него"""
    file = await telegram_bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    return file_url

def extract_buttons(message: types.Message):
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            button_row = []
            for button in row:
                if button.url:
                    button_row.append({
                        "text": button.text,
                        "url": button.url
                    })
            if button_row:
                buttons.append(button_row)
    return buttons

@dp.message()
async def forward_to_max(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        sender_name = message.from_user.full_name or message.from_user.username or "Пользователь"
        logging.info(f"📨 Получено от: {sender_name} (бот: {message.from_user.is_bot})")
        
        # Текст сообщения (подпись для медиа или обычный текст)
        text = message.text or message.caption or ''
        
        # Извлекаем кнопки
        buttons = extract_buttons(message)
        
        # Определяем тип контента и отправляем
        if message.photo:
            # Фото
            photo = message.photo[-1]  # максимальное качество
            photo_url = await download_file(photo.file_id)
            
            if buttons:
                # Если есть кнопки, отправляем с клавиатурой
                await max_bot.send_photo(
                    chat_id=MAX_CHANNEL_ID,
                    photo=photo_url,
                    caption=text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                await max_bot.send_photo(
                    chat_id=MAX_CHANNEL_ID,
                    photo=photo_url,
                    caption=text
                )
            logging.info(f"✅ Фото переслано")
            
        elif message.video:
            # Видео
            video_url = await download_file(message.video.file_id)
            
            if buttons:
                await max_bot.send_video(
                    chat_id=MAX_CHANNEL_ID,
                    video=video_url,
                    caption=text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                await max_bot.send_video(
                    chat_id=MAX_CHANNEL_ID,
                    video=video_url,
                    caption=text
                )
            logging.info(f"✅ Видео переслано")
            
        elif message.voice:
            # Голосовое сообщение
            voice_url = await download_file(message.voice.file_id)
            
            if buttons:
                await max_bot.send_voice(
                    chat_id=MAX_CHANNEL_ID,
                    voice=voice_url,
                    caption=text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                await max_bot.send_voice(
                    chat_id=MAX_CHANNEL_ID,
                    voice=voice_url,
                    caption=text
                )
            logging.info(f"✅ Голосовое переслано")
            
        elif message.document:
            # Документ
            doc_url = await download_file(message.document.file_id)
            filename = message.document.file_name or "document"
            
            if buttons:
                await max_bot.send_document(
                    chat_id=MAX_CHANNEL_ID,
                    document=doc_url,
                    caption=text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                await max_bot.send_document(
                    chat_id=MAX_CHANNEL_ID,
                    document=doc_url,
                    caption=text
                )
            logging.info(f"✅ Документ переслан")
            
        elif message.text:
            # Простой текст
            if buttons:
                await max_bot.send_message(
                    chat_id=MAX_CHANNEL_ID,
                    text=text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                await max_bot.send_message(
                    chat_id=MAX_CHANNEL_ID,
                    text=text
                )
            logging.info(f"✅ Текст переслан")
        
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ Бот запущен со всеми функциями!\n\n"
        "Поддерживается:\n"
        "• Текст без префиксов\n"
        "• Фото с подписями\n"
        "• Видео\n"
        "• Голосовые сообщения\n"
        "• Документы\n"
        "• Кнопки-ссылки\n"
        "• Сообщения от ботов"
    )

async def main():
    logging.info("🚀 Бот запускается со всеми функциями...")
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
