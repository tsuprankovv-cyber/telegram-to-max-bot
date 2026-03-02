import os
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# === НАСТРОЙКА ПОДРОБНОГО ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === КЛАСС ДЛЯ РАБОТЫ С MAX API (ИСПРАВЛЕННЫЙ) ===
class MaxBot:
    def __init__(self, token: str):
        self.token = token
        # ПРАВИЛЬНЫЙ URL ИЗ ДОКУМЕНТАЦИИ MAX
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        logger.info("✅ MaxBot инициализирован с правильным URL")
        
    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def _request(self, endpoint: str, data: dict):
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"{self.token}",  # Токен без "Bearer"
            "Content-Type": "application/json"
        }
        
        logger.info(f"📤 Отправка запроса в MAX: {endpoint}")
        logger.info(f"   URL: {url}")
        logger.info(f"   Данные: {str(data)[:200]}...")
        
        try:
            async with self.session.post(url, headers=headers, json=data) as resp:
                response = await resp.json()
                logger.info(f"📥 Ответ от MAX (статус {resp.status}): {response}")
                return response
        except Exception as e:
            logger.error(f"❌ Ошибка соединения с MAX: {e}")
            raise
    
    async def send_message(self, chat_id: str, text: str, reply_markup=None):
        """Отправка текстового сообщения"""
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("messages", data)
    
    async def send_photo(self, chat_id: str, photo: str, caption=None, reply_markup=None):
        """Отправка фото"""
        data = {
            "chat_id": chat_id,
            "photo": photo,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("messages", data)
    
    async def send_video(self, chat_id: str, video: str, caption=None, reply_markup=None):
        """Отправка видео"""
        data = {
            "chat_id": chat_id,
            "video": video,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("messages", data)
    
    async def send_voice(self, chat_id: str, voice: str, caption=None, reply_markup=None):
        """Отправка голосового сообщения"""
        data = {
            "chat_id": chat_id,
            "voice": voice,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("messages", data)
    
    async def send_document(self, chat_id: str, document: str, caption=None, reply_markup=None):
        """Отправка документа"""
        data = {
            "chat_id": chat_id,
            "document": document,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("messages", data)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

# Проверка наличия всех переменных
if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

telegram_bot = Bot(token=TELEGRAM_TOKEN)
max_bot = MaxBot(token=MAX_TOKEN)
dp = Dispatcher()

async def download_file(file_id: str) -> str:
    """Скачивает файл из Telegram и возвращает ссылку на него"""
    try:
        logger.info(f"📥 Скачивание файла: {file_id}")
        file = await telegram_bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        logger.info(f"✅ Файл скачан: {file_url}")
        return file_url
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания: {e}")
        raise

def extract_buttons(message: types.Message):
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        logger.info(f"🔘 Найдены кнопки: {len(message.reply_markup.inline_keyboard)} рядов")
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
    # Проверка источника
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    # ПОДРОБНОЕ ЛОГИРОВАНИЕ
    logger.info("="*60)
    logger.info("📨 НОВОЕ СООБЩЕНИЕ:")
    logger.info(f"🆔 ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name} (ID: {message.from_user.id})")
    
    # Информация о пересылке
    if message.forward_date:
        logger.info("🔄 ПЕРЕСЛАННОЕ:")
        if message.forward_from_chat:
            logger.info(f"  📢 Из канала: {message.forward_from_chat.title}")
    
    # Тип контента
    text = message.text or message.caption or ''
    if text:
        logger.info(f"📝 Текст: {text[:100]}...")
    
    if message.photo:
        logger.info(f"🖼 ФОТО: {len(message.photo)} версий")
        photo = message.photo[-1]
        logger.info(f"   file_id: {photo.file_id}")
    elif message.video:
        logger.info(f"🎥 ВИДЕО")
    elif message.voice:
        logger.info(f"🎤 ГОЛОСОВОЕ")
    elif message.document:
        logger.info(f"📄 ДОКУМЕНТ")
    elif message.text:
        logger.info(f"📝 ТЕКСТ")
    
    logger.info("="*60)
    
    # ПЕРЕСЫЛКА
    try:
        # Текст с информацией об источнике
        final_text = text
        if message.forward_from_chat and text:
            final_text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
            logger.info(f"📝 Добавлена подпись об источнике")
        
        buttons = extract_buttons(message)
        reply_markup = {"inline_keyboard": buttons} if buttons else None
        
        if message.photo:
            photo = message.photo[-1]
            photo_url = await download_file(photo.file_id)
            logger.info(f"📤 Отправка фото в MAX...")
            result = await max_bot.send_photo(MAX_CHANNEL_ID, photo_url, final_text, reply_markup)
            logger.info(f"✅ Фото переслано, ответ: {result}")
            
        elif message.video:
            video_url = await download_file(message.video.file_id)
            logger.info(f"📤 Отправка видео в MAX...")
            result = await max_bot.send_video(MAX_CHANNEL_ID, video_url, final_text, reply_markup)
            logger.info(f"✅ Видео переслано, ответ: {result}")
            
        elif message.voice:
            voice_url = await download_file(message.voice.file_id)
            logger.info(f"📤 Отправка голосового в MAX...")
            result = await max_bot.send_voice(MAX_CHANNEL_ID, voice_url, final_text, reply_markup)
            logger.info(f"✅ Голосовое переслано, ответ: {result}")
            
        elif message.document:
            doc_url = await download_file(message.document.file_id)
            logger.info(f"📤 Отправка документа в MAX...")
            result = await max_bot.send_document(MAX_CHANNEL_ID, doc_url, final_text, reply_markup)
            logger.info(f"✅ Документ переслан, ответ: {result}")
            
        elif message.text:
            logger.info(f"📤 Отправка текста в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
            logger.info(f"✅ Текст переслан, ответ: {result}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при пересылке: {e}")
        logger.exception("Детали ошибки:")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ Бот-пересыльщик запущен\n"
        f"📤 Откуда: группа {TELEGRAM_GROUP_ID}\n"
        f"📥 Куда: канал {MAX_CHANNEL_ID}\n"
        f"🌐 MAX API: https://platform-api.max.ru"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Команда для тестирования подключения к MAX"""
    await message.answer("🔄 Тестирую подключение к MAX API...")
    try:
        result = await max_bot.send_message(
            MAX_CHANNEL_ID,
            "🔄 Тестовое сообщение от бота"
        )
        await message.answer(f"✅ Подключение работает! Ответ: {result}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def main():
    logger.info("="*60)
    logger.info("🚀 БОТ-ПЕРЕСЫЛЬЩИК ЗАПУСКАЕТСЯ")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info(f"🌐 MAX API URL: https://platform-api.max.ru")
    logger.info("="*60)
    
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
