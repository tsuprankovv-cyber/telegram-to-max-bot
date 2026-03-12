import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional

# === НАСТРОЙКА МАКСИМАЛЬНОГО ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

logger.info("="*80)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
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
    """Преобразует кириллицу в латиницу"""
    result = []
    for char in text:
        if char in TRANSLIT_DICT:
            result.append(TRANSLIT_DICT[char])
        else:
            result.append(char)
    return ''.join(result)

def safe_filename(filename: str) -> str:
    """
    Создаёт безопасное имя файла:
    - Кириллица -> транслит
    - Спецсимволы -> _
    """
    # Разделяем имя и расширение
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    
    # Транслитерация
    name = transliterate(name)
    
    # Заменяем спецсимволы на _
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Убираем множественные подчеркивания
    name = re.sub(r'_+', '_', name)
    # Убираем подчеркивания в начале и конце
    name = name.strip('_')
    
    if not name:
        name = 'file'
    
    result = f"{name}.{ext}" if ext else name
    logger.debug(f"🏷️ Имя файла: '{filename}' -> '{result}'")
    return result

class MediaUploader:
    """Загрузчик медиа с правильным получением токенов"""
    
    def __init__(self, token: str):
        self.token = token
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
            logger.debug("🔌 Сессия создана")
    
    async def create_upload(self, media_type: str) -> dict:
        """Создание загрузки"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 [ЗАГРУЗКА] Создание загрузки для {media_type}")
        logger.debug(f"   URL: {url}")
        logger.debug(f"   Params: {params}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            response_text = await resp.text()
            logger.debug(f"📥 [ОТВЕТ] Статус: {resp.status}")
            logger.debug(f"📥 [ОТВЕТ] Тело: {response_text[:500]}")
            
            if resp.status == 200:
                result = json.loads(response_text)
                logger.info(f"✅ [ЗАГРУЗКА] Успешно")
                logger.debug(f"   URL загрузки: {result.get('url', '')}")
                if result.get('token'):
                    logger.debug(f"   Токен: {result['token'][:20]}...")
                return result
            else:
                logger.error(f"❌ [ЗАГРУЗКА] Ошибка {resp.status}")
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        """
        Загружает файл и возвращает токен
        """
        await self.ensure_session()
        
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        logger.info(f"📤 [ФАЙЛ] Загрузка: {filename}")
        logger.debug(f"   Тип: {content_type}")
        logger.debug(f"   Размер: {len(file_data)} байт")
        logger.debug(f"   URL: {upload_url}")
        
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            response_text = await resp.text()
            logger.debug(f"📥 [ФАЙЛ] Статус: {resp.status}")
            logger.debug(f"📥 [ФАЙЛ] Ответ: {response_text[:500]}")
            
            if resp.status == 200:
                logger.info(f"✅ [ФАЙЛ] {filename} загружен")
                
                # Пробуем получить токен из JSON
                try:
                    result = json.loads(response_text)
                    if result.get('token'):
                        logger.info(f"✅ [ТОКЕН] Получен из JSON")
                        return result['token']
                except:
                    pass
                
                # Для видео/аудио токен может быть в первом ответе
                logger.warning(f"⚠️ [ТОКЕН] Не найден в ответе")
                return None
            else:
                logger.error(f"❌ [ФАЙЛ] Ошибка {resp.status}")
                return None
    
    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка видео (РАБОЧАЯ ВЕРСИЯ)"""
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎥 [ВИДЕО] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("video")
            
            # Для видео токен приходит сразу
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                logger.error("❌ [ВИДЕО] Не получен токен или URL")
                self.stats["video_failed"] += 1
                return None
            
            if await self.upload_file(upload_url, file_data, safe_name):
                logger.info(f"⏳ [ВИДЕО] Ожидание обработки (2 сек)...")
                await asyncio.sleep(2)
                self.stats["video_ok"] += 1
                logger.info(f"✅ [ВИДЕО] {safe_name} готов, токен: {token[:20]}...")
                return token
            else:
                self.stats["video_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [ВИДЕО] Ошибка: {e}")
            self.stats["video_failed"] += 1
            return None
    
    async def upload_document(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        """Загрузка документа (токен после загрузки)"""
        try:
            safe_name = safe_filename(filename)
            logger.info(f"📄 [ДОКУМЕНТ] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [ДОКУМЕНТ] Не получен URL")
                self.stats["documents_failed"] += 1
                return None
            
            token = await self.upload_file(upload_url, file_data, safe_name)
            
            if token:
                self.stats["documents_ok"] += 1
                logger.info(f"✅ [ДОКУМЕНТ] {safe_name} готов")
                return (token, safe_name)
            else:
                self.stats["documents_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [ДОКУМЕНТ] Ошибка: {e}")
            self.stats["documents_failed"] += 1
            return None
    
    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[Tuple[str, str]]:
        """Загрузка аудио (как документ)"""
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎵 [АУДИО] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [АУДИО] Не получен URL")
                self.stats["audio_failed"] += 1
                return None
            
            token = await self.upload_file(upload_url, file_data, safe_name)
            
            if token:
                self.stats["audio_ok"] += 1
                logger.info(f"✅ [АУДИО] {safe_name} готов")
                return (token, safe_name)
            else:
                self.stats["audio_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [АУДИО] Ошибка: {e}")
            self.stats["audio_failed"] += 1
            return None
    
    async def upload_voice(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка голосового"""
        try:
            safe_name = safe_filename(filename)
            logger.info(f"🎤 [ГОЛОСОВОЕ] Загрузка: {filename} -> {safe_name}")
            
            upload_info = await self.create_upload("audio")
            token = upload_info.get('token')
            upload_url = upload_info.get('url')
            
            if not token or not upload_url:
                logger.error("❌ [ГОЛОСОВОЕ] Не получен токен или URL")
                self.stats["voice_failed"] += 1
                return None
            
            if await self.upload_file(upload_url, file_data, safe_name):
                logger.info(f"⏳ [ГОЛОСОВОЕ] Ожидание обработки (2 сек)...")
                await asyncio.sleep(2)
                self.stats["voice_ok"] += 1
                logger.info(f"✅ [ГОЛОСОВОЕ] готово")
                return token
            else:
                self.stats["voice_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [ГОЛОСОВОЕ] Ошибка: {e}")
            self.stats["voice_failed"] += 1
            return None

class TelegramDownloader:
    """Класс для скачивания файлов из Telegram"""
    
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_info(self, file_id: str) -> dict:
        """Получает информацию о файле"""
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        logger.debug(f"🔍 [TG] Запрос информации: {file_id}")
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                logger.debug(f"✅ [TG] Путь: {data['result']['file_path']}")
                return data['result']
            else:
                error = await resp.text()
                raise Exception(f"Ошибка получения информации: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл из Telegram"""
        await self.ensure_session()
        
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        
        url = f"{self.file_url}/{file_path}"
        logger.info(f"📥 [TG] Скачивание: {filename}")
        logger.debug(f"   URL: {url}")
        
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                logger.info(f"✅ [TG] Скачано {len(data)} байт")
                return (data, filename)
            else:
                error = await resp.text()
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Инициализируем
uploader = MediaUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

# === ТЕКСТОВЫЕ ФУНКЦИИ (без изменений) ===
def format_text_with_entities(text: str, entities: list) -> str:
    if not entities or not text:
        return text or ""
    
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    result = text
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        fragment = result[start:end]
        
        if entity.type == "bold":
            replacement = f"**{fragment}**"
        elif entity.type == "italic":
            replacement = f"*{fragment}*"
        elif entity.type == "underline":
            replacement = f"++{fragment}++"
        elif entity.type == "strikethrough":
            replacement = f"~~{fragment}~~"
        elif entity.type == "text_link":
            replacement = f"[{fragment}]({entity.url})"
        elif entity.type == "blockquote":
            replacement = f"> {fragment}"
        else:
            continue
        
        result = result[:start] + replacement + result[end:]
    
    return result

def is_heading(text: str, entities: list) -> bool:
    if not entities or not text:
        return False
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    first = sorted_entities[0]
    
    if first.offset != 0 or first.type != "bold":
        return False
    
    last_pos = 0
    last_bold_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        last_bold_end = e.offset + e.length
        last_pos = last_bold_end
    
    if last_bold_end == 0:
        return False
    
    text_after = text[last_bold_end:].lstrip()
    return bool(text_after)

def extract_heading_text(text: str, entities: list) -> tuple[str, str, list]:
    if not entities:
        return "", text, []
    
    sorted_entities = sorted(entities, key=lambda e: e.offset)
    
    last_pos = 0
    heading_end = 0
    
    for e in sorted_entities:
        if e.offset != last_pos:
            break
        if e.type != "bold":
            break
        heading_end = e.offset + e.length
        last_pos = heading_end
    
    if heading_end == 0:
        return "", text, entities
    
    heading = text[:heading_end]
    after_raw = text[heading_end:]
    after_stripped = after_raw.lstrip()
    spaces = len(after_raw) - len(after_stripped)
    
    remaining_entities = []
    shift = heading_end + spaces
    
    for e in sorted_entities:
        if e.offset >= heading_end:
            new_e = type('Entity', (), {})()
            new_e.offset = e.offset - shift
            new_e.length = e.length
            new_e.type = e.type
            if hasattr(e, 'url'):
                new_e.url = e.url
            remaining_entities.append(new_e)
    
    return heading, after_stripped, remaining_entities

def process_text_part(text: str, entities: list) -> str:
    if not text:
        return ""
    
    if is_heading(text, entities):
        heading, rest, rest_entities = extract_heading_text(text, entities)
        heading_formatted = f"# {heading}"
        
        if rest:
            rest_formatted = format_text_with_entities(rest, rest_entities)
            return f"{heading_formatted}\n\n{rest_formatted}"
        return heading_formatted
    
    return format_text_with_entities(text, entities)

async def process_media_message(message: types.Message) -> Tuple[str, List[dict]]:
    """Обработка сообщения"""
    attachments = []
    text = message.caption or ""
    
    logger.info("="*80)
    logger.info(f"📨 ОБРАБОТКА СООБЩЕНИЯ ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    try:
        # ФОТО
        if message.photo:
            logger.info("🖼️ [ФОТО] Обработка")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1
            logger.info("✅ [ФОТО] Готово")
        
        # ВИДЕО (рабочая версия)
        elif message.video:
            logger.info("🎥 [ВИДЕО] Обработка")
            file_data, filename = await downloader.download_file(message.video.file_id)
            token = await uploader.upload_video(file_data, filename)
            if token:
                attachments.append({
                    "type": "video",
                    "payload": {"token": token}
                })
        
        # АУДИО
        elif message.audio:
            logger.info("🎵 [АУДИО] Обработка")
            file_data, filename = await downloader.download_file(message.audio.file_id)
            result = await uploader.upload_audio(file_data, filename)
            if result:
                token, safe_name = result
                attachments.append({
                    "type": "file",
                    "payload": {"token": token, "name": safe_name}
                })
        
        # ГОЛОСОВЫЕ
        elif message.voice:
            logger.info("🎤 [ГОЛОСОВОЕ] Обработка")
            file_data, filename = await downloader.download_file(message.voice.file_id)
            token = await uploader.upload_voice(file_data, filename)
            if token:
                attachments.append({
                    "type": "audio",
                    "payload": {"token": token}
                })
        
        # ДОКУМЕНТЫ
        elif message.document:
            file_name = message.document.file_name
            logger.info(f"📄 [ДОКУМЕНТ] Обработка: {file_name}")
            
            file_data, _ = await downloader.download_file(message.document.file_id)
            
            # Определяем тип
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt']:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
                    logger.info(f"✅ [ДОКУМЕНТ] {safe_name} готов")
            
            elif ext in ['mp4', 'mov', 'avi']:
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "video",
                        "payload": {"token": token}
                    })
            
            elif ext in ['mp3', 'wav', 'ogg']:
                result = await uploader.upload_audio(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
            
            else:
                result = await uploader.upload_document(file_data, file_name)
                if result:
                    token, safe_name = result
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": safe_name}
                    })
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info(f"📦 ВСЕГО ВЛОЖЕНИЙ: {len(attachments)}")
    return text, attachments

async def send_to_max(text: str, attachments: List[dict] = None):
    """Отправка в MAX"""
    if not attachments:
        logger.warning("⚠️ Нет вложений")
        return False
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text or " ",
        "format": "markdown",
        "attachments": attachments
    }
    
    logger.info("="*80)
    logger.info(f"📤 ОТПРАВКА В MAX")
    logger.info(f"📎 Вложений: {len(attachments)}")
    
    for i, att in enumerate(attachments, 1):
        att_type = att['type']
        payload = att['payload']
        if 'name' in payload:
            logger.info(f"   {i}. {att_type}: {payload['name']}")
        elif 'url' in payload:
            logger.info(f"   {i}. {att_type}: URL")
        elif 'token' in payload:
            logger.info(f"   {i}. {att_type}: токен {payload['token'][:20]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                
                logger.info(f"📥 Статус: {resp.status}")
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    logger.error(f"❌ Ошибка {resp.status}: {response_text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward(message: types.Message):
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    text, attachments = await process_media_message(message)
    
    if not attachments:
        logger.warning("⚠️ Нет вложений")
        return
    
    if message.caption:
        text_entities = message.caption_entities
    else:
        text_entities = message.entities
    
    if text and text_entities:
        text = process_text_part(text, text_entities)
    
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        text = f"📢 Переслано из {source}:\n\n{text}"
    
    await send_to_max(text, attachments)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК MAX**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 📄 PDF, DOC, XLS (транслит)\n"
        "• 🎥 Видео\n"
        "• 🎵 Аудио (файлы)\n"
        "• 🎤 Голосовые\n"
        "• 🖼️ Фото\n"
        "• 📦 Пакетная отправка\n\n"
        "📊 Статистика: /stats"
    )

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = uploader.stats
    await message.answer(
        f"📊 **СТАТИСТИКА:**\n\n"
        f"📄 Документы: ✅ {stats['documents_ok']} | ❌ {stats['documents_failed']}\n"
        f"🎥 Видео: ✅ {stats['video_ok']} | ❌ {stats['video_failed']}\n"
        f"🎵 Аудио: ✅ {stats['audio_ok']} | ❌ {stats['audio_failed']}\n"
        f"🎤 Голосовые: ✅ {stats['voice_ok']} | ❌ {stats['voice_failed']}\n"
        f"🖼️ Фото: ✅ {stats['photo_ok']}"
    )

async def cleanup():
    if downloader.session:
        await downloader.session.close()
    if uploader.session:
        await uploader.session.close()
    logger.info(f"📊 Итог: {uploader.stats}")

async def main():
    logger.info("🚀 ЗАПУСК БОТА")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
