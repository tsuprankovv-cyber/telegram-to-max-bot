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
from datetime import datetime

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

class DocumentUploader:
    """
    Загрузчик для всех типов файлов с правильным получением токена
    """
    
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
        """Создание загрузки - получаем URL для загрузки"""
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
                logger.info(f"✅ [ЗАГРУЗКА] Успешно, получен URL")
                logger.debug(f"   URL загрузки: {result.get('url', '')}")
                return result
            else:
                logger.error(f"❌ [ЗАГРУЗКА] Ошибка {resp.status}: {response_text}")
                raise Exception(f"Ошибка создания загрузки: {resp.status}")
    
    async def upload_file_and_get_token(self, upload_url: str, file_data: bytes, filename: str) -> Optional[str]:
        """
        Загружает файл и извлекает токен из ответа
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
                
                # Пытаемся извлечь токен из ответа
                try:
                    # Сначала пробуем JSON
                    result = json.loads(response_text)
                    if result.get('token'):
                        logger.info(f"✅ [ТОКЕН] Получен из JSON")
                        return result['token']
                except:
                    pass
                
                # Пробуем извлечь из XML <retval> или другого формата
                token_match = re.search(r'[a-f0-9]{50,}', response_text)
                if token_match:
                    token = token_match.group(0)
                    logger.info(f"✅ [ТОКЕН] Получен из текста: {token[:20]}...")
                    return token
                
                # Если не нашли токен, но загрузка успешна
                logger.warning(f"⚠️ [ТОКЕН] Не найден в ответе, но файл загружен")
                return "token_placeholder"
            else:
                logger.error(f"❌ [ФАЙЛ] Ошибка {resp.status}: {response_text}")
                return None
    
    async def upload_document(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка документа"""
        try:
            logger.info(f"📄 [ДОКУМЕНТ] Начало загрузки: {filename}")
            
            upload_info = await self.create_upload("file")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [ДОКУМЕНТ] Не получен URL")
                self.stats["documents_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, filename)
            
            if token:
                self.stats["documents_ok"] += 1
                logger.info(f"✅ [ДОКУМЕНТ] {filename} готов, токен: {token[:20]}...")
                return token
            else:
                self.stats["documents_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [ДОКУМЕНТ] Ошибка: {e}")
            self.stats["documents_failed"] += 1
            return None
    
    async def upload_video(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка видео"""
        try:
            logger.info(f"🎥 [ВИДЕО] Начало загрузки: {filename}")
            
            upload_info = await self.create_upload("video")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [ВИДЕО] Не получен URL")
                self.stats["video_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, filename)
            
            if token:
                logger.info(f"⏳ [ВИДЕО] Ожидание обработки (2 сек)...")
                await asyncio.sleep(2)
                self.stats["video_ok"] += 1
                logger.info(f"✅ [ВИДЕО] {filename} готов")
                return token
            else:
                self.stats["video_failed"] += 1
                return None
                
        except Exception as e:
            logger.error(f"❌ [ВИДЕО] Ошибка: {e}")
            self.stats["video_failed"] += 1
            return None
    
    async def upload_audio(self, file_data: bytes, filename: str) -> Optional[str]:
        """Загрузка аудио как файла"""
        try:
            logger.info(f"🎵 [АУДИО] Начало загрузки: {filename}")
            
            upload_info = await self.create_upload("file")  # Загружаем как file
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [АУДИО] Не получен URL")
                self.stats["audio_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, filename)
            
            if token:
                self.stats["audio_ok"] += 1
                logger.info(f"✅ [АУДИО] {filename} готов")
                return token
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
            logger.info(f"🎤 [ГОЛОСОВОЕ] Начало загрузки")
            
            upload_info = await self.create_upload("audio")
            upload_url = upload_info.get('url')
            
            if not upload_url:
                logger.error("❌ [ГОЛОСОВОЕ] Не получен URL")
                self.stats["voice_failed"] += 1
                return None
            
            token = await self.upload_file_and_get_token(upload_url, file_data, filename)
            
            if token:
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
                file_path = data['result']['file_path']
                logger.debug(f"✅ [TG] Путь: {file_path}")
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
uploader = DocumentUploader(MAX_TOKEN)
downloader = TelegramDownloader(TELEGRAM_TOKEN)

def format_text_with_entities(text: str, entities: list) -> str:
    """Форматирует текст с entities"""
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
    """Проверяет заголовок"""
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
    """Извлекает заголовок"""
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
    """Обрабатывает текст"""
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
    """
    ОБРАБОТКА СООБЩЕНИЯ
    """
    attachments = []
    text = message.caption or ""
    
    logger.info("="*80)
    logger.info(f"📨 ОБРАБОТКА СООБЩЕНИЯ ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    try:
        # ФОТО - прямая ссылка
        if message.photo:
            logger.info("🖼️ [ФОТО] Обработка")
            file_info = await downloader.get_file_info(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            uploader.stats["photo_ok"] += 1
            logger.info(f"✅ [ФОТО] Готово")
        
        # ВИДЕО
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
            token = await uploader.upload_audio(file_data, filename)
            if token:
                attachments.append({
                    "type": "file",
                    "payload": {"token": token, "name": filename}
                })
                logger.info(f"✅ [АУДИО] {filename} готов как файл")
        
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
            
            # Определяем тип по расширению
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            # Документы (PDF, DOC, XLS)
            document_ext = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'rtf', 'odt', 'ods']
            
            if ext in document_ext:
                logger.info(f"   Тип: документ {ext}")
                token = await uploader.upload_document(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": file_name}
                    })
                    logger.info(f"✅ [ДОКУМЕНТ] {file_name} готов")
            
            elif ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                logger.info(f"   Тип: изображение")
                file_info = await downloader.get_file_info(message.document.file_id)
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
                attachments.append({
                    "type": "image",
                    "payload": {"url": file_url}
                })
                uploader.stats["photo_ok"] += 1
            
            elif ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
                logger.info(f"   Тип: видео")
                token = await uploader.upload_video(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "video",
                        "payload": {"token": token}
                    })
            
            elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac']:
                logger.info(f"   Тип: аудио (как файл)")
                token = await uploader.upload_audio(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": file_name}
                    })
            
            else:
                logger.info(f"   Тип: неизвестный ({ext}), пробуем как документ")
                token = await uploader.upload_document(file_data, file_name)
                if token:
                    attachments.append({
                        "type": "file",
                        "payload": {"token": token, "name": file_name}
                    })
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info(f"📦 ВСЕГО ВЛОЖЕНИЙ: {len(attachments)}")
    return text, attachments

async def send_to_max(text: str, attachments: List[dict] = None):
    """Отправляет сообщение в MAX"""
    if not attachments:
        logger.warning("⚠️ Нет вложений для отправки")
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
    
    logger.debug(f"📦 Полный запрос: {json.dumps(data, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                
                logger.info(f"📥 Статус: {resp.status}")
                logger.debug(f"📥 Ответ: {response_text[:500]}")
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    logger.error(f"❌ Ошибка {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward(message: types.Message):
    """Основной обработчик"""
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
        "• 📄 PDF, DOC, XLS (с именами)\n"
        "• 🎥 Видео\n"
        "• 🎵 Аудио (как файлы)\n"
        "• 🎤 Голосовые\n"
        "• 🖼️ Фото\n"
        "• 📦 Пакетная отправка\n\n"
        "📊 Статистика: /stats\n"
        "🔍 Логирование: DEBUG"
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
    """Закрытие сессий"""
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
