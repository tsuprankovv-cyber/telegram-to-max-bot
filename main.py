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

# === КЛАСС ДЛЯ РАБОТЫ С MAX API (ВСТРОЕН) ===
class MaxBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.max.ru/v1"  # Если не работает, замените на актуальный URL
        self.session = None
        logger.info("✅ MaxBot инициализирован")
        
    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def _request(self, endpoint: str, data: dict):
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"📤 Отправка запроса в MAX: {endpoint}")
        async with self.session.post(url, headers=headers, json=data) as resp:
            response = await resp.json()
            logger.debug(f"📥 Ответ от MAX: {response}")
            return response
    
    async def send_message(self, chat_id: str, text: str, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("sendMessage", data)
    
    async def send_photo(self, chat_id: str, photo: str, caption=None, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "photo": photo,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("sendPhoto", data)
    
    async def send_video(self, chat_id: str, video: str, caption=None, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "video": video,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("sendVideo", data)
    
    async def send_voice(self, chat_id: str, voice: str, caption=None, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "voice": voice,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("sendVoice", data)
    
    async def send_document(self, chat_id: str, document: str, caption=None, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "document": document,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        return await self._request("sendDocument", data)

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
        
        buttons = extract_buttons(message)
        
        if message.photo:
            photo = message.photo[-1]
            photo_url = await download_file(photo.file_id)
            await max_bot.send_photo(MAX_CHANNEL_ID, photo_url, final_text, 
                                    {"inline_keyboard": buttons} if buttons else None)
            logger.info("✅ Фото переслано")
            
        elif message.video:
            video_url = await download_file(message.video.file_id)
            await max_bot.send_video(MAX_CHANNEL_ID, video_url, final_text,
                                    {"inline_keyboard": buttons} if buttons else None)
            logger.info("✅ Видео переслано")
            
        elif message.voice:
            voice_url = await download_file(message.voice.file_id)
            await max_bot.send_voice(MAX_CHANNEL_ID, voice_url, final_text,
                                    {"inline_keyboard": buttons} if buttons else None)
            logger.info("✅ Голосовое переслано")
            
        elif message.document:
            doc_url = await download_file(message.document.file_id)
            await max_bot.send_document(MAX_CHANNEL_ID, doc_url, final_text,
                                      {"inline_keyboard": buttons} if buttons else None)
            logger.info("✅ Документ переслан")
            
        elif message.text:
            await max_bot.send_message(MAX_CHANNEL_ID, final_text,
                                     {"inline_keyboard": buttons} if buttons else None)
            logger.info("✅ Текст переслан")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ Бот-пересыльщик запущен\n"
        f"📤 Откуда: группа {TELEGRAM_GROUP_ID}\n"
        f"📥 Куда: канал {MAX_CHANNEL_ID}"
    )

async def main():
    logger.info("🚀 Бот запускается...")
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
