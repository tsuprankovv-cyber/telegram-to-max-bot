import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional, Dict, Any

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO, # Можно изменить на DEBUG для детальной отладки
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

logger.info("="*80)
logger.info("🚀 ЗАПУСК БОТА-ПЕРЕВОДЧИКА (TELEGRAM -> MAX)")
logger.info(f"👥 TG Group: {TELEGRAM_GROUP_ID}")
logger.info(f"📢 MAX Channel: {MAX_CHANNEL_ID}")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === ТРАНСЛИТЕРАЦИЯ (для имен файлов) ===
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
    result = []
    for char in text:
        result.append(TRANSLIT_DICT.get(char, char))
    return ''.join(result)

def safe_filename(filename: str) -> str:
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    name = transliterate(name)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    if not name:
        name = 'file'
    return f"{name}.{ext}" if ext else name

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
# 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: КОНВЕРТАЦИЯ ПОЗИЦИЙ (UTF-16 -> Unicode)
# ============================================================

def tg_offset_to_py(text: str, tg_offset: int) -> int:
    """
    Конвертирует позицию из Telegram (UTF-16 code units) в позицию Python (Unicode code points).
    
    Telegram считает эмодзи (например 🎉) как 2 символа (суррогатная пара).
    Python считает их как 1 символ.
    
    Алгоритм: проходим по строке и считаем 'вес' каждого символа.
    Если код символа > 0xFFFF, он занимает 2 единицы в UTF-16.
    """
    py_pos = 0
    utf16_pos = 0
    
    while utf16_pos < tg_offset and py_pos < len(text):
        char = text[py_pos]
        code = ord(char)
        # Символы вне Basic Multilingual Plane (> 0xFFFF) занимают 2 UTF-16 единицы
        utf16_pos += 2 if code > 0xFFFF else 1
        py_pos += 1
        
    return py_pos

def format_text(telegram_text: str, entities: list) -> str:
    """
    Преобразует текст с entity из Telegram в HTML.
    Использует корректную конвертацию позиций.
    """
    if not telegram_text:
        return ""
    if not entities:
        return telegram_text

    logger.debug(f"📝 Обработка текста: {len(telegram_text)} символов, {len(entities)} сущностей")
    
    formats = []
    
    for entity in entities:
        # Поддержка объекта aiogram и словаря
        if hasattr(entity, 'offset'):
            tg_start = entity.offset
            tg_len = entity.length
            e_type = entity.type
            url = getattr(entity, 'url', None)
        else:
            tg_start = entity['offset']
            tg_len = entity['length']
            e_type = entity['type']
            url = entity.get('url')
        
        # Конвертация позиций
        py_start = tg_offset_to_py(telegram_text, tg_start)
        py_end = tg_offset_to_py(telegram_text, tg_start + tg_len)
        
        # Защита от выхода за границы
        py_start = max(0, py_start)
        py_end = min(len(telegram_text), py_end)
        
        if py_start >= py_end:
            logger.warning(f"⚠️ Пропущена сущность {e_type}: некорректный диапазон [{py_start}:{py_end}]")
            continue
            
        fragment = telegram_text[py_start:py_end]
        formats.append({
            'start': py_start,
            'end': py_end,
            'type': e_type,
            'text': fragment,
            'url': url
        })
        logger.debug(f"  ✅ {e_type}: TG[{tg_start}+{tg_len}] -> PY[{py_start}:{py_end}] '{fragment[:20]}...'")

    # Сортируем от конца к началу, чтобы вставка тегов не сдвигала позиции следующих сущностей
    formats.sort(key=lambda x: -x['start'])
    
    result = telegram_text
    
    # HTML теги для разных типов
    html_tags = {
        'bold': ('<b>', '</b>'),
        'italic': ('<i>', '</i>'),
        'underline': ('<u>', '</u>'),
        'strikethrough': ('<s>', '</s>'),
        'code': ('<code>', '</code>'),
        'pre': ('<pre>', '</pre>'),
        'blockquote': ('<blockquote>', '</blockquote>'),
        'spoiler': ('<tg-spoiler>', '</tg-spoiler>')
    }
    
    for fmt in formats:
        s, e = fmt['start'], fmt['end']
        t = fmt['type']
        txt = fmt['text']
        url = fmt['url']
        
        replacement = None
        
        if t == 'text_link' and url:
            # Экранирование URL для безопасности
            safe_url = url.replace('"', '&quot;')
            replacement = f'<a href="{safe_url}">{txt}</a>'
        elif t in html_tags:
            open_tag, close_tag = html_tags[t]
            replacement = f"{open_tag}{txt}{close_tag}"
        else:
            # Неизвестный тип, пропускаем
            continue
            
        if replacement:
            result = result[:s] + replacement + result[e:]
            
    # === ВАЛИДАЦИЯ ===
    # Удаляем все теги и проверяем, совпадает ли текст с оригиналом
    clean_check = re.sub(r'<[^>]+>', '', result)
    if clean_check != telegram_text:
        logger.error("❌ ВАЛИДАЦИЯ НЕ ПРОЙДЕНА! Текст изменился при форматировании.")
        logger.error(f"   Оригинал: {repr(telegram_text[:50])}")
        logger.error(f"   Результат: {repr(clean_check[:50])}")
        # Возвращаем чистый текст без форматирования, чтобы не сломать систему
        return telegram_text
        
    logger.debug("✅ Форматирование успешно пройдено")
    return result

# === КЛАССЫ ДЛЯ РАБОТЫ С МЕДИА И API ===

class MediaUploader:
    def __init__(self, token: str):
        self.token = token
        # Убраны лишние пробелы в URL
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        self.stats = {
            "documents_ok": 0, "documents_failed": 0,
            "video_ok": 0, "video_failed": 0,
            "audio_ok": 0, "audio_failed": 0,
            "voice_ok": 0, "voice_failed": 0,
            "photo_ok": 0
        }

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def create_upload(self, media_type: str) -> dict:
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                raise Exception(f"Ошибка создания загрузки ({media_type}): {resp.status} - {text}")

    async def upload_file_only(self, upload_url: str, file_data: bytes, filename: str) -> bool:
        await self.ensure_session()
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
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
                    return result.get('token')
                except:
                    return None
            return None

    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            upload_info = await self.create_upload("video")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["video_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1) # Небольшая пауза для обработки на сервере
                self.stats["video_ok"] += 1
                return token
            else:
                self.stats["video_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка видео: {e}")
            self.stats["video_failed"] += 1
            return None

    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
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
            else:
                self.stats["documents_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка документа: {e}")
            self.stats["documents_failed"] += 1
            return None

    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        try:
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
            else:
                self.stats["audio_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка аудио: {e}")
            self.stats["audio_failed"] += 1
            return None

    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        try:
            safe_name = safe_filename(filename)
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                self.stats["voice_failed"] += 1
                return None
                
            if await self.upload_file_only(upload_url, file_data, safe_name):
                await asyncio.sleep(1)
                self.stats["voice_ok"] += 1
                return token
            else:
                self.stats["voice_failed"] += 1
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка голосового: {e}")
            self.stats["voice_failed"] += 1
            return None

class TelegramDownloader:
    def __init__(self, token: str):
        self.token = token
        # Убраны лишние пробелы
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.session = None

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def get_file_info(self, file_id: str) -> dict:
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            else:
                raise Exception(f"Ошибка getInfo: {resp.status}")

    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        await self.ensure_session()
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        url = f"{self.file_url}/{file_path}"
        
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return (data, filename)
            else:
                raise Exception(f"Ошибка download: {resp.status}")

# Инициализация глобальных объектов
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max(text: str, attachments: List[dict] = None):
    # Убраны лишние пробелы в URL
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

    logger.info(f"📤 Отправка в MAX (текст: {len(text)} симв., вложений: {len(attachments) if attachments else 0})")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                if resp.status == 200:
                    logger.info("✅ Успешно отправлено в MAX")
                    return True
                else:
                    logger.error(f"❌ Ошибка MAX {resp.status}: {response_text[:200]}")
                    return False
    except Exception as e:
        logger.error(f"❌ Исключение при отправке: {e}")
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

        elif message.video:
            logger.info("🎥 Обработка видео")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({"type": "video", "payload": {"token": token}})

        elif message.audio:
            logger.info("🎵 Обработка аудио")
            file_data, _ = await downloader.download_file(message.audio.file_id)
            original_name = message.audio.file_name or "audio.mp3"
            result = await uploader.upload_audio(file_data, original_name)
            if result:
                token, safe_name = result
                attachments.append({"type": "file", "payload": {"token": token, "name": safe_name}})

        elif message.voice:
            logger.info("🎤 Обработка голосового")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, "voice.ogg")
            if token:
                attachments.append({"type": "audio", "payload": {"token": token}})

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
        logger.error(f"❌ Ошибка обработки медиа: {e}")
        
    return text, attachments

@dp.message()
async def forward(message: types.Message):
    # Фильтр по группе
    if str(message.chat.id) != str(TELEGRAM_GROUP_ID):
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
        final_text = format_text(raw_text, entities)
    
    # Добавление префикса пересылки если нужно
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title or "Неизвестный источник"
        final_text = f"📢 Переслано из {source}:\n\n{final_text}"

    # 2. Обработка медиа
    if message.photo or message.video or message.audio or message.voice or message.document:
        logger.info("📦 Обработка медиа-вложений")
        _, media_attachments = await process_media_message(message)
        attachments.extend(media_attachments)
        
        if not attachments:
            logger.warning("⚠️ Медиа найдено, но не удалось загрузить ни одного вложения")
            # Если есть текст, отправляем только его
            if not final_text:
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
        await send_to_max(final_text, attachments if attachments else None)
    else:
        logger.warning("⚠️ Нечего отправлять (нет текста и медиа)")

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("✅ Бот запущен и готов к пересылке сообщений.\nИспользуйте /stats для проверки статистики.")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    text = (
        f"📊 **СТАТИСТИКА ЗАГРУЗОК:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']}"
    )
    await message.answer(text, parse_mode="Markdown")

async def cleanup():
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()

async def main():
    await telegram_bot.delete_webhook(drop_pending_updates=True)
    logger.info("✨ Бот запущен в режиме polling...")
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота...")
    finally:
        asyncio.run(cleanup())
