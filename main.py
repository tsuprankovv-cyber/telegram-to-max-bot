вот смотри вот этот код отправляет как надо. всё работает. что мы не могли додумать?
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
from typing import List, Tuple, Optional, Dict, Any

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
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
DEBUG_FORMATTING = os.getenv('DEBUG_FORMATTING', 'false').lower() == 'true'

if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    for name, val in [('TELEGRAM_TOKEN', TELEGRAM_TOKEN), ('TELEGRAM_GROUP_ID', TELEGRAM_GROUP_ID), 
                      ('MAX_TOKEN', MAX_TOKEN), ('MAX_CHANNEL_ID', MAX_CHANNEL_ID)]:
        logger.error(f"   {name}: {'✅' if val else '❌'}")
    raise ValueError("Missing environment variables")

logger.info("="*80)
logger.info("🚀 ЗАПУСК БОТА-ПЕРЕВОДЧИКА (TELEGRAM -> MAX)")
logger.info(f"👥 TG Group: {TELEGRAM_GROUP_ID}")
logger.info(f"📢 MAX Channel: {MAX_CHANNEL_ID}")
logger.info(f"🔍 DEBUG_FORMATTING: {DEBUG_FORMATTING}")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

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
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                buttons.append(button_row)
    return buttons

# ============================================================
# 🔥 ФОРМАТИРОВАНИЕ ЧЕРЕЗ aiogram (поддерживает вложенность!)
# ============================================================

def format_text(telegram_text: str, entities: list, message_id: int = None) -> str:
    """
    Преобразует текст с entity из Telegram в HTML.
    ✅ Поддерживает перекрывающиеся сущности: <b><i>жирный курсив</i></b>
    ✅ Использует встроенный html_decoration из aiogram
    """
    msg_prefix = f"[MSG {message_id}]" if message_id else ""
    
    if not telegram_text:
        logger.info(f"{msg_prefix} 📭 Пустой текст")
        return ""
    
    if not entities:
        logger.info(f"{msg_prefix} 🔤 Текст без сущностей")
        return telegram_text

    logger.info(f"{msg_prefix} 📝 Форматирование: {len(telegram_text)} символов, {len(entities)} сущностей")
    
    if DEBUG_FORMATTING:
        logger.debug(f"{msg_prefix} 📄 ОРИГИНАЛ: {repr(telegram_text)}")
        for i, e in enumerate(entities):
            off = e.offset if hasattr(e, 'offset') else e['offset']
            ln = e.length if hasattr(e, 'length') else e['length']
            tp = e.type if hasattr(e, 'type') else e['type']
            logger.debug(f"{msg_prefix}   Entity #{i+1}: {tp} [{off}+{ln}]")

    try:
        # ✅ Встроенный метод aiogram корректно обрабатывает:
        # - Перекрывающиеся сущности (bold+italic на одном диапазоне)
        # - Вложенные сущности (bold внутри italic)
        # - Сущности с URL (text_link)
        # - Конвертацию UTF-16 offset → Unicode code points
        result = html_decoration.unparse(telegram_text, entities)
        
        logger.info(f"{msg_prefix} ✅ Форматирование через aiogram успешно")
        if DEBUG_FORMATTING:
            logger.debug(f"{msg_prefix} 📄 РЕЗУЛЬТАТ: {repr(result)}")
            logger.debug(f"{msg_prefix} 📄 РЕЗУЛЬТАТ (вид): {result}")
        return result
        
    except Exception as e:
        logger.exception(f"{msg_prefix} ❌ Ошибка форматирования: {e}")
        logger.warning(f"{msg_prefix} ⚠️ Возвращаем чистый текст")
        return telegram_text

# === КЛАССЫ ДЛЯ РАБОТЫ С МЕДИА И API ===

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
            self.session = aiohttp.ClientSession()
            logger.info("🔗 Создана новая aiohttp сессия для MediaUploader")

    async def create_upload(self, media_type: str) -> dict:
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.debug(f"📤 POST {url} params={params}")
        async with self.session.post(url, headers=headers, params=params) as resp:
            resp_text = await resp.text()
            logger.debug(f"📥 Ответ: {resp.status} {resp_text[:200]}")
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(f"Ошибка создания загрузки ({media_type}): {resp.status} - {resp_text}")

    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.debug(f"📤 Загрузка файла: {filename} ({len(file_data)} байт, type={content_type})")
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            resp_text = await resp.text()
            logger.debug(f"📥 Ответ загрузки: {resp.status}")
            return resp.status == 200

    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            if resp.status == 200:
                try:
                    result = await resp.json()
                    token = result.get('token')
                    logger.debug(f"✅ Получен токен: {token[:20] if token else None}...")
                    return token
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON: {e}")
                    return None
            else:
                logger.error(f"❌ Ошибка загрузки файла: {resp.status}")
                return None

    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎬 Загрузка видео: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                logger.error(f"❌ Не получен token или url из upload_info: {upload_info}")
                self.stats["video_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1)
                self.stats["video_ok"] += 1
                logger.info(f"✅ Видео загружено: {safe_name}")
                return token
            else:
                self.stats["video_failed"] += 1
                logger.error(f"❌ Ошибка загрузки видео: {safe_name}")
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение при загрузке видео: {e}")
            self.stats["video_failed"] += 1
            return None

    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"📄 Загрузка документа: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["documents_failed"] += 1
                return None
                
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            if token:
                self.stats["documents_ok"] += 1
                logger.info(f"✅ Документ загружен: {safe_name}")
                return (token, safe_name)
            else:
                self.stats["documents_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение при загрузке документа: {e}")
            self.stats["documents_failed"] += 1
            return None

    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎵 Загрузка аудио: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                self.stats["audio_failed"] += 1
                return None
                
            token = await self.upload_file_and_get_token(upload_url, file_data, safe_name)
            if token:
                self.stats["audio_ok"] += 1
                logger.info(f"✅ Аудио загружено: {safe_name}")
                return (token, safe_name)
            else:
                self.stats["audio_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение при загрузке аудио: {e}")
            self.stats["audio_failed"] += 1
            return None

    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎤 Загрузка голосового: {safe_name} ({len(file_data)} байт)")
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1)
                self.stats["voice_ok"] += 1
                logger.info(f"✅ Голосовое загружено: {safe_name}")
                return token
            else:
                self.stats["voice_failed"] += 1
                return None
        except Exception as e:
            logger.exception(f"❌ Исключение при загрузке голосового: {e}")
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
            self.session = aiohttp.ClientSession()
            logger.info("🔗 Создана новая aiohttp сессия для TelegramDownloader")

    async def get_file_info(self, file_id: str) -> dict:
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        logger.debug(f"📤 POST {url} file_id={file_id[:20]}...")
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                logger.debug(f"📥 FileInfo: {data.get('result', {}).get('file_path', 'N/A')}")
                return data['result']
            else:
                text = await resp.text()
                raise Exception(f"Ошибка getInfo: {resp.status} - {text}")

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        await self.ensure_session()
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        url = f"{self.file_url}/{file_path}"
        
        logger.info(f"📥 Скачивание файла: {filename} ({file_info.get('file_size', '?')} байт)")
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                logger.info(f"✅ Файл скачан: {filename} ({len(data)} байт)")
                return (data, filename)
            else:
                raise Exception(f"Ошибка download: {resp.status}")

# Инициализация глобальных объектов
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max(text: str, attachments: List[dict] = None):
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }

    data = {
        "text": text or " ",
        "format": "html"
    }

    if attachments:
        data["attachments"] = attachments

    logger.info(f"📤 Отправка в MAX: текст={len(text)} симв., вложений={len(attachments) if attachments else 0}")
    if DEBUG_FORMATTING:
        logger.debug(f"📦 Payload: {json.dumps(data, ensure_ascii=False)[:500]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                if resp.status == 200:
                    logger.info("✅ Успешно отправлено в MAX")
                    return True
                else:
                    logger.error(f"❌ Ошибка MAX {resp.status}: {response_text[:500]}")
                    return False
    except Exception as e:
        logger.exception(f"❌ Исключение при отправке в MAX: {e}")
        return False

async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
    attachments = []
    text = message.caption or ""
    
    try:
        if message.photo:
            logger.info("🖼️ Обработка фото")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"{downloader.file_url}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1
            logger.info(f"✅ Фото добавлено: {photo_url}")

        elif message.video:
            logger.info("🎥 Обработка видео")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({"type": "video", "payload": {"token": token}})
                logger.info(f"✅ Видео добавлено с токеном: {token[:20] if token else None}...")

        elif message.audio:
            logger.info("🎵 Обработка аудио")
            file_data, _ = await downloader.download_file(message.audio.file_id)
            original_name = message.audio.file_name or "audio.mp3"
            result = await uploader.upload_audio(file_data, original_name)
            if result:
                token, safe_name = result
                attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})
                logger.info(f"✅ Аудио добавлено: {safe_name}")

        elif message.voice:
            logger.info("🎤 Обработка голосового")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({"type": "audio", "payload": {"token": token}})
                logger.info(f"✅ Голосовое добавлено с токеном: {token[:20] if token else None}...")

        elif message.document:
            file_name = message.document.file_name
            logger.info(f"📄 Обработка документа: {file_name}")
            file_data, _ = await downloader.download_file(message.document.file_id)
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            # Логика определения типа файла для MAX
            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt']:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})
            elif ext in ['mp4', 'mov', 'avi']:
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({"type": "video", "payload": {"token": token}})
            elif ext in ['mp3', 'wav', 'ogg']:
                result = await uploader.upload_audio(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})
            else:
                # По умолчанию как документ
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})

    except Exception as e:
        logger.exception(f"❌ Ошибка обработки медиа: {e}")
        
    return text, attachments

@dp.message()
async def forward(message: types.Message):
    # Фильтр по группе
    if str(message.chat.id) != str(TELEGRAM_GROUP_ID):
        logger.debug(f"🚫 Сообщение из другого чата {message.chat.id}, игнорируем")
        return

    logger.info(f"📨 Получено сообщение ID: {message.message_id} из чата {message.chat.id}")
    
    buttons = extract_buttons(message)
    attachments = []
    final_text = ""
    
    # 1. Обработка текста и форматирования
    if message.text:
        raw_text = message.text
        entities = message.entities or []
        logger.info("📝 Чисто текстовое сообщение")
    elif message.caption:
        raw_text = message.caption
        entities = message.caption_entities or []
        logger.info("📝 Сообщение с подписью (медиа)")
    else:
        raw_text = ""
        entities = []
        logger.info("📝 Сообщение без текста")

    if raw_text:
        final_text = format_text(raw_text, entities, message_id=message.message_id)
        logger.info(f"✍️ Итоговый текст: {len(final_text)} символов")
        if DEBUG_FORMATTING:
            logger.debug(f"📄 Итоговый текст (repr): {repr(final_text[:200])}...")
    
    # Добавление префикса пересылки если нужно
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title or "Неизвестный источник"
        final_text = f"📢 Переслано из {source}:\n\n{final_text}"
        logger.info(f"🔁 Добавлен префикс пересылки из: {source}")

    # 2. Обработка медиа
    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Обработка медиа-вложений")
        _, media_attachments = await process_media_message(message)
        attachments.extend(media_attachments)
        logger.info(f"📎 Добавлено вложений: {len(media_attachments)}")
        
        if not attachments and (message.photo or message.video or message.audio or message.voice or message.document):
            logger.warning("⚠️ Медиа найдено, но не удалось загрузить ни одного вложения")
            if not final_text:
                logger.warning("⚠️ Нет текста для отправки, пропускаем сообщение")
                return 

    # 3. Обработка кнопок
    if buttons:
        attachments.append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
        logger.info(f"🔘 Добавлено кнопок: {len(buttons)} рядов")

    # 4. Отправка
    if final_text or attachments:
        success = await send_to_max(final_text, attachments if attachments else None)
        if success:
            logger.info(f"✅ Сообщение {message.message_id} успешно переслано")
        else:
            logger.error(f"❌ Не удалось переслать сообщение {message.message_id}")
    else:
        logger.warning("⚠️ Нечего отправлять (нет текста и медиа)")

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("✅ Бот запущен и готов к пересылке сообщений.\nИспользуйте /stats для проверки статистики.")
    logger.info(f"👤 Пользователь {message.from_user.id} выполнил /start")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    text = (
        f"📊 **СТАТИСТИКА ЗАГРУЗОК:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']} | ❌ {stats['photo_failed']}"
    )
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"👤 Пользователь {message.from_user.id} запросил статистику")

async def cleanup():
    logger.info("🧹 Закрытие сессий...")
    if downloader.session:
        await downloader.session.close()
        logger.info("✅ Сессия TelegramDownloader закрыта")
    if uploader.session:
        await uploader.session.close()
        logger.info("✅ Сессия MediaUploader закрыта")

async def main():
    await telegram_bot.delete_webhook(drop_pending_updates=True)
    logger.info("✨ Бот запущен в режиме polling...")
    try:
        await dp.start_polling(telegram_bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Получен сигнал остановки")
    finally:
        await cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота...")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
