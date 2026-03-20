# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.text_decorations import html_decoration
from aiogram.client.session.aiohttp import AiohttpSession
from typing import List, Tuple, Optional
from aiohttp import web

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '').strip()
MAX_TOKEN = os.getenv('MAX_TOKEN', '').strip()
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID', '').strip()

logger.info("="*80)
logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (TELEGRAM -> MAX)")
logger.info(f"👥 TG Group: {TELEGRAM_GROUP_ID}")
logger.info(f"📢 MAX Channel: {MAX_CHANNEL_ID}")

# 🔹 ПРОВЕРКА ПЕРЕМЕННЫХ
missing = []
if not TELEGRAM_TOKEN: missing.append('TELEGRAM_TOKEN')
if not TELEGRAM_GROUP_ID: missing.append('TELEGRAM_GROUP_ID')
if not MAX_TOKEN: missing.append('MAX_TOKEN')
if not MAX_CHANNEL_ID: missing.append('MAX_CHANNEL_ID')

if missing:
    logger.error("❌ ОТСУТСТВУЮТ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
    for var in missing:
        logger.error(f"   - {var}")
    raise ValueError(f"Missing: {', '.join(missing)}")

logger.info("✅ Все переменные установлены")
logger.info("="*80)

# === СОЗДАЁМ DP СРАЗУ ===
dp = Dispatcher()

# === ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ===
telegram_bot = None
uploader = None
downloader = None

# === ТРАНСЛИТЕРАЦИЯ ===
TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}

def transliterate(text: str) -> str:
    return ''.join(TRANSLIT_DICT.get(char, char) for char in text)

def safe_filename(filename: str) -> str:
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    name = transliterate(name)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return f"{name or 'file'}.{ext}" if ext else (name or 'file')

# === ИЗВЛЕЧЕНИЕ КНОПОК ===
def extract_buttons(message: types.Message) -> list:
    buttons = []
    if message.reply_markup and hasattr(message.reply_markup, 'inline_keyboard'):
        for row in message.reply_markup.inline_keyboard:
            button_row = []
            for btn in row:
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({"type": "link", "text": btn.text, "url": btn.url})
            if button_row:
                buttons.append(button_row)
    return buttons

# === ФОРМАТИРОВАНИЕ ТЕКСТА ===
def format_text(telegram_text: str, entities: list, message_id: int = None) -> str:
    if not telegram_text:
        return ""
    if not entities:
        return telegram_text
    try:
        return html_decoration.unparse(telegram_text, entities)
    except Exception as e:
        logger.error(f"❌ Ошибка форматирования: {e}")
        return telegram_text

# === ЗАГРУЗКА МЕДИА ===
class MediaUploader:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        self.stats = {
            "documents_ok": 0, "documents_failed": 0,
            "video_ok": 0, "video_failed": 0,
            "audio_ok": 0, "audio_failed": 0,
            "voice_ok": 0, "voice_failed": 0,
            "photo_ok": 0, "photo_failed": 0
        }

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))

    async def create_upload(self, media_type: str) -> dict:
        await self.ensure_session()
        try:
            async with self.session.post(f"{self.base_url}/uploads", headers={"Authorization": self.token}, params={"type": media_type}) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {}
        except Exception as e:
            logger.error(f"❌ create_upload: {e}")
            return {}

    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        await self.ensure_session()
        try:
            data = aiohttp.FormData()
            data.add_field('file', file_data, filename=filename)
            async with self.session.post(upload_url, data=data) as resp:
                return resp.status == 200
        except:
            return False

    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        await self.ensure_session()
        try:
            data = aiohttp.FormData()
            data.add_field('file', file_data, filename=filename)
            async with self.session.post(upload_url, data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get('token')
                return None
        except:
            return None

    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        safe_name = safe_filename(filename)
        upload_info = await self.create_upload("video")
        token, upload_url = upload_info.get('token'), upload_info.get('url')
        if not token or not upload_url:
            self.stats["video_failed"] += 1
            return None
        if await self.upload_file_only(upload_url, file_data, safe_name):
            await asyncio.sleep(1)
            self.stats["video_ok"] += 1
            return token
        self.stats["video_failed"] += 1
        return None

    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        safe_name = safe_filename(filename)
        upload_info = await self.create_upload("file")
        upload_url = upload_info.get('url')
        if not upload_url:
            self.stats["documents_failed"] += 1
            return None
        token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
        if token:
            self.stats["documents_ok"] += 1
            return (token, safe_name)
        self.stats["documents_failed"] += 1
        return None

    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        safe_name = safe_filename(filename)
        upload_info = await self.create_upload("file")
        upload_url = upload_info.get('url')
        if not upload_url:
            self.stats["audio_failed"] += 1
            return None
        token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
        if token:
            self.stats["audio_ok"] += 1
            return (token, safe_name)
        self.stats["audio_failed"] += 1
        return None

    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        safe_name = safe_filename(filename)
        upload_info = await self.create_upload("audio")
        token, upload_url = upload_info.get('token'), upload_info.get('url')
        if not token or not upload_url:
            self.stats["voice_failed"] += 1
            return None
        if await self.upload_file_only(upload_url, file_data, safe_name):
            await asyncio.sleep(1)
            self.stats["voice_ok"] += 1
            return token
        self.stats["voice_failed"] += 1
        return None

class TelegramDownloader:
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.session = None

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))

    async def get_file_info(self, file_id: str) -> dict:
        await self.ensure_session()
        async with self.session.post(f"{self.api_url}/getFile", json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            raise Exception(f"Ошибка getInfo: {resp.status}")

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        await self.ensure_session()
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        async with self.session.get(f"{self.file_url}/{file_path}") as resp:
            if resp.status == 200:
                return (await resp.read(), filename)
            raise Exception(f"Ошибка download: {resp.status}")

# === ОТПРАВКА В MAX ===
async def send_to_max(text: str, attachments: List[dict] = None):
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {"Authorization": MAX_TOKEN, "Content-Type": "application/json"}
    data = {"text": text or " ", "format": "html"}
    if attachments:
        data["attachments"] = attachments
    
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ Отправлено в MAX")
                    return True
                logger.error(f"❌ MAX {resp.status}: {await resp.text()[:500]}")
                return False
    except Exception as e:
        logger.error(f"❌ send_to_max: {e}")
        return False

# === ОБРАБОТКА МЕДИА ===
async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
    attachments = []
    try:
        if message.photo:
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            attachments.append({"type": "image", "payload": {"url": f"{downloader.file_url}/{file_info['file_path']}"}})
            uploader.stats["photo_ok"] += 1
        elif message.video:
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({"type": "video", "payload": {"token": token}})
        elif message.audio:
            file_data, _ = await downloader.download_file(message.audio.file_id)
            result = await uploader.upload_audio(file_data, message.audio.file_name or "audio.mp3")
            if result:
                attachments.append({"type": "file", "payload": {"token": result[0], "name": result[1]}})
        elif message.voice:
            file_data, _ = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({"type": "audio", "payload": {"token": token}})
        elif message.document:
            file_data, _ = await downloader.download_file(message.document.file_id)
            ext = message.document.file_name.lower().split('.')[-1] if '.' in message.document.file_name else ''
            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt']:
                result = await uploader.upload_document(file_data, message.document.file_name)
                if result:
                    attachments.append({"type": "file", "payload": {"token": result[0], "name": result[1]}})
            elif ext in ['mp4', 'mov', 'avi']:
                token = await uploader.upload_video(file_data, message.document.file_name)
                if token:
                    attachments.append({"type": "video", "payload": {"token": token}})
            elif ext in ['mp3', 'wav', 'ogg']:
                result = await uploader.upload_audio(file_data, message.document.file_name)
                if result:
                    attachments.append({"type": "file", "payload": {"token": result[0], "name": result[1]}})
            else:
                result = await uploader.upload_document(file_data, message.document.file_name)
                if result:
                    attachments.append({"type": "file", "payload": {"token": result[0], "name": result[1]}})
    except Exception as e:
        logger.error(f"❌ process_media_message: {e}")
    return message.caption or "", attachments

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
@dp.message()
async def forward(message: types.Message):
    if str(message.chat.id) != str(TELEGRAM_GROUP_ID):
        return
    
    logger.info(f"📨 MSG {message.message_id} из {message.chat.id}")
    
    buttons = extract_buttons(message)
    attachments = []
    final_text = ""
    
    raw_text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    if raw_text:
        final_text = format_text(raw_text, entities, message_id=message.message_id)
    
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title or "Неизвестный источник"
        final_text = f"📢 Переслано из {source}:\n\n{final_text}"
    
    if message.photo or message.video or message.audio or message.voice or message.document:
        _, media_attachments = await process_media_message(message)
        attachments.extend(media_attachments)
        if not attachments and not final_text:
            return
    
    if buttons:
        attachments.append({"type": "inline_keyboard", "payload": {"buttons": buttons}})
    
    if final_text or attachments:
        success = await send_to_max(final_text, attachments if attachments else None)
        if success:
            logger.info(f"✅ MSG {message.message_id} переслано")
        else:
            logger.error(f"❌ MSG {message.message_id} НЕ переслано")

# === КОМАНДЫ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("✅ Бот запущен.\nИспользуйте /stats для статистики.")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    await message.answer(
        f"📊 **СТАТИСТИКА:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']} | ❌ {stats['photo_failed']}",
        parse_mode="Markdown"
    )

# === ОЧИСТКА ===
async def cleanup():
    logger.info("🧹 Закрытие сессий...")
    if downloader and downloader.session:
        await downloader.session.close()
    if uploader and uploader.session:
        await uploader.session.close()
    if telegram_bot and telegram_bot.session:
        await telegram_bot.session.close()
    logger.info("✅ Сессии закрыты")

# === HEALTH CHECK (для UptimeRobot) ===
async def health_handler(request):
    return web.json_response({
        "status": "ok",
        "bot": telegram_bot.username if telegram_bot else "not started",
        "timestamp": asyncio.get_event_loop().time()
    })

async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("🏥 Health check запущен на порту 8080")

# === ЗАПУСК ===
async def main():
    global telegram_bot, uploader, downloader
    
    # 🔹 Создаём бота
    telegram_bot = Bot(token=TELEGRAM_TOKEN)
    uploader = MediaUploader(MAX_TOKEN)
    downloader = TelegramDownloader(TELEGRAM_TOKEN)
    
    # 🔹 Webhook
    try:
        await asyncio.wait_for(telegram_bot.delete_webhook(drop_pending_updates=True), timeout=30)
        logger.info("✅ Webhook удалён")
    except Exception as e:
        logger.warning(f"⚠️ Webhook: {e}")
    
    # 🔹 Проверка соединения
    try:
        me = await telegram_bot.get_me()
        logger.info(f"✅ Бот авторизован: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Telegram: {e}")
        raise
    
    logger.info("✨ Запуск polling...")
    
    # 🔹 ЗАПУСК POLLING (БЕЗ __all__!)
    try:
        # 🔹 skip_updates=True сбрасывает старые обновления
        await dp.start_polling(telegram_bot, skip_updates=True)
        logger.info("✅ Polling запущен успешно")
    except asyncio.CancelledError:
        logger.info("🛑 Polling остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка polling: {e}", exc_info=True)
        raise
    finally:
        await cleanup()

# === ЗАПУСК ===
if __name__ == '__main__':
    try:
        # 🔹 Запускаем health check + бота
        async def run_all():
            await start_web_server()
            await main()
        
        logger.info("🚀 Запуск всех сервисов...")
        asyncio.run(run_all())
        
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по сигналу...")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
