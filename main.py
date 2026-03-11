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

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class TelegramDownloader:
    """Класс для скачивания файлов из Telegram"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']['file_path']
            else:
                raise Exception(f"Ошибка получения пути файла: {resp.status}")

tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max_channel(text: str, attachments: list = None, buttons: list = None):
    """Отправляет сообщение в канал MAX - РАБОЧАЯ ВЕРСИЯ"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Формируем сообщение
    message_data = {"text": text}
    if attachments:
        message_data["attachments"] = attachments
    
    # Добавляем кнопки если есть
    if buttons:
        message_data["attachments"] = message_data.get("attachments", [])
        message_data["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
    
    # ПРАВИЛЬНАЯ СТРУКТУРА из рабочего кода
    data = {
        "recipient": {
            "chat_id": str(MAX_CHANNEL_ID)  # ID как строка внутри recipient
        },
        "message": message_data
    }
    
    logger.info("="*60)
    logger.info(f"📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📋 Recipient chat_id: {MAX_CHANNEL_ID}")
    logger.info(f"📝 Текст: {text[:100]}...")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО ОТПРАВЛЕНО!")
                    logger.info(f"📥 Ответ: {response_text[:200]}")
                    return True
                else:
                    logger.error(f"❌ ОШИБКА MAX: {resp.status}")
                    logger.error(f"📥 Ответ: {response_text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

def get_media_type(message: types.Message) -> str:
    """Определяет тип медиа в сообщении"""
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.audio:
        return 'audio'
    elif message.voice:
        return 'voice'
    elif message.document:
        return 'document'
    elif message.animation:
        return 'animation'
    return None

async def process_media(message: types.Message) -> list:
    """Обрабатывает медиа из сообщения - как в рабочем коде"""
    attachments = []
    media_type = get_media_type(message)
    
    if not media_type:
        return attachments
    
    try:
        # Для фото - быстрая отправка по URL
        if media_type == 'photo':
            file_id = message.photo[-1].file_id
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"🖼️ Фото обработано: {photo_url[:50]}...")
        
        # Для остальных типов (упрощенно)
        else:
            logger.info(f"📦 {media_type} - пока поддерживается только фото")
            # Здесь можно добавить обработку других типов
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
    
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
    
    try:
        logger.info("="*60)
        logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
        logger.info(f"👤 От: {message.from_user.full_name} (бот: {message.from_user.is_bot})")
        
        # Текст сообщения
        text = message.text or message.caption or ""
        if text:
            logger.info(f"📝 Текст: {text[:100]}...")
        
        # Информация о пересылке
        if message.forward_date:
            logger.info("🔄 ЭТО ПЕРЕСЛАННОЕ СООБЩЕНИЕ")
            if message.forward_from_chat:
                logger.info(f"   Из канала: {message.forward_from_chat.title}")
                text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
            elif message.forward_from:
                logger.info(f"   От: {message.forward_from.full_name}")
                text = f"👤 Переслано от {message.forward_from.full_name}:\n\n{text}"
        
        # Обрабатываем медиа
        attachments = await process_media(message)
        
        # Извлекаем кнопки
        buttons = await extract_buttons(message)
        
        # Отправляем в MAX
        success = await send_to_max_channel(text, attachments, buttons)
        
        if success:
            logger.info("✅ СООБЩЕНИЕ ПЕРЕСЛАНО УСПЕШНО")
        else:
            logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали:")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **Бот-пересыльщик MAX**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📋 **Поддерживается:**\n"
        "• Текст\n"
        "• Фото (через URL)\n"
        "• Пересланные сообщения\n"
        "• Кнопки-ссылки"
    )

async def cleanup():
    if tg_downloader.session:
        await tg_downloader.session.close()

async def main():
    logger.info("="*60)
    logger.info("🚀 БОТ-ПЕРЕСЫЛЬЩИК ЗАПУСКАЕТСЯ")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info("="*60)
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    finally:
        asyncio.run(cleanup())
