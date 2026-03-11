import os
import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

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

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class TelegramDownloader:
    """Класс для работы с файлами Telegram"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']['file_path']
            else:
                raise Exception(f"Ошибка получения пути файла: {resp.status}")

tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max_channel(text: str, attachments: list = None):
    """Отправляет сообщение в канал MAX - РАБОЧАЯ ВЕРСИЯ из вашего старого кода"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Формируем данные КАК В РАБОЧЕМ КОДЕ
    data = {
        "recipient": {
            "chat_id": str(MAX_CHANNEL_ID)  # ID как строка внутри recipient
        },
        "message": {
            "text": text
        }
    }
    
    # Добавляем вложения если есть
    if attachments:
        data["message"]["attachments"] = attachments
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📋 Recipient chat_id: {MAX_CHANNEL_ID}")
    logger.info(f"📝 Текст: {text[:100]}...")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
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

async def process_media(message: types.Message) -> list:
    """Обрабатывает фото из сообщения"""
    attachments = []
    
    if message.photo:
        try:
            file_id = message.photo[-1].file_id
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"🖼️ Фото обработано")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки фото: {e}")
    
    return attachments

async def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            button_row = []
            for btn in row:
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                buttons.append(button_row)
        
        if buttons:
            logger.info(f"🔘 Найдено {len(buttons)} рядов кнопок")
    
    return buttons

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщения из Telegram в MAX"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    
    text = message.text or message.caption or ""
    if text:
        logger.info(f"📝 Текст: {text}")
    
    # Добавляем подпись для пересланных сообщений
    if message.forward_date and message.forward_from_chat:
        text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
        logger.info(f"🔄 Добавлена подпись об источнике")
    
    # Обрабатываем медиа
    attachments = await process_media(message)
    
    # Извлекаем кнопки
    buttons = await extract_buttons(message)
    if buttons:
        attachments.append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
    
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
        "✅ Бот-пересыльщик MAX\n\n"
        f"📤 Источник: группа {TELEGRAM_GROUP_ID}\n"
        f"📥 Приёмник: канал {MAX_CHANNEL_ID}"
    )

@dp.message(Command("test_max"))
async def cmd_test_max(message: types.Message):
    """Тестовая отправка"""
    await message.answer("🔄 Тестовая отправка...")
    success = await send_to_max_channel("🔄 Тестовое сообщение")
    if success:
        await message.answer("✅ Успешно!")
    else:
        await message.answer("❌ Ошибка")

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
