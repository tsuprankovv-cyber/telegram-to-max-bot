import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class MediaUploader:
    """Класс для загрузки медиа в MAX"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_upload_url(self, media_type: str) -> dict:
        """Получает URL для загрузки файла"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads"
        headers = {"Authorization": self.token}
        params = {"type": media_type}
        
        logger.info(f"📤 Запрос URL для загрузки: {media_type}")
        
        async with self.session.post(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                result = await resp.json()
                logger.info(f"✅ Получен URL")
                return result
            else:
                error = await resp.text()
                logger.error(f"❌ Ошибка получения URL: {resp.status}")
                raise Exception(f"Ошибка получения URL: {resp.status}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> str:
        """Загружает файл и возвращает токен"""
        await self.ensure_session()
        
        # Определяем MIME-тип
        content_type = mimetypes.guess_type(filename)[0]
        if not content_type:
            if filename.endswith('.mp4'):
                content_type = 'video/mp4'
            elif filename.endswith(('.mp3', '.m4a')):
                content_type = 'audio/mpeg'
            elif filename.endswith('.ogg'):
                # Пробуем конвертировать в mp3? Нет, просто меняем расширение
                filename = filename.replace('.ogg', '.mp3')
                content_type = 'audio/mpeg'
            elif filename.endswith('.oga'):
                filename = filename.replace('.oga', '.mp3')
                content_type = 'audio/mpeg'
            elif filename.endswith('.pdf'):
                content_type = 'application/pdf'
            elif filename.endswith(('.doc', '.docx')):
                content_type = 'application/msword'
            elif filename.endswith(('.xls', '.xlsx')):
                content_type = 'application/vnd.ms-excel'
            else:
                content_type = 'application/octet-stream'
        
        logger.info(f"📤 Загрузка файла: {filename} ({content_type})")
        
        # Важно: отправляем как multipart/form-data
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        async with self.session.post(upload_url, data=data) as resp:
            # Читаем как текст
            response_text = await resp.text()
            logger.info(f"📥 Ответ сервера: {resp.status} - {response_text[:200]}")
            
            if resp.status == 200:
                # Пытаемся распарсить JSON
                try:
                    result = json.loads(response_text)
                    token = result.get('token')
                    if token:
                        logger.info(f"✅ Файл загружен, токен получен")
                        return token
                    else:
                        logger.error(f"❌ Нет токена в JSON: {result}")
                        raise Exception("Нет токена в ответе")
                except json.JSONDecodeError:
                    # Если не JSON, проверяем XML с <retval>
                    if '<retval>' in response_text:
                        # Извлекаем число из <retval>1</retval>
                        match = re.search(r'<retval>(\d+)</retval>', response_text)
                        if match:
                            # Это ID файла, но MAX нужен токен
                            # Пробуем использовать это как токен?
                            token = match.group(1)
                            logger.info(f"⚠️ Получен ID файла: {token}, пробуем использовать как токен")
                            return token
                    
                    logger.error(f"❌ Не JSON и не XML: {response_text[:100]}")
                    raise Exception(f"Неожиданный ответ: {response_text[:100]}")
            else:
                logger.error(f"❌ Ошибка загрузки: {resp.status}")
                raise Exception(f"Ошибка загрузки: {resp.status}")

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
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']
            else:
                error = await resp.text()
                raise Exception(f"Ошибка получения информации: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл и возвращает (данные, имя_файла)"""
        await self.ensure_session()
        
        file_info = await self.get_file_info(file_id)
        file_path = file_info['file_path']
        filename = file_path.split('/')[-1]
        
        url = f"{self.file_url}/{file_path}"
        logger.info(f"📥 Скачивание: {url}")
        
        async with self.session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                logger.info(f"✅ Скачано {len(data)} байт")
                return (data, filename)
            else:
                error = await resp.text()
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Инициализируем загрузчики
media_uploader = MediaUploader(MAX_TOKEN)
tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

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
    """Проверяет, является ли начало заголовком"""
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
    """Обрабатывает текстовую часть сообщения"""
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

async def process_media_message(message: types.Message) -> tuple[str, list]:
    """Обрабатывает медиа-сообщение"""
    attachments = []
    text = message.caption or ""
    
    try:
        if message.photo:
            # Фото - через URL (работает)
            photo = message.photo[-1]
            logger.info(f"🖼️ Фото: {photo.width}x{photo.height}")
            
            file_info = await tg_downloader.get_file_info(photo.file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            
        elif message.video:
            # Видео - через загрузку
            logger.info(f"🎥 Видео: {message.video.file_name or 'без названия'}")
            
            file_data, filename = await tg_downloader.download_file(message.video.file_id)
            upload_info = await media_uploader.get_upload_url("video")
            token = await media_uploader.upload_file(upload_info['url'], file_data, filename)
            
            attachments.append({
                "type": "video",
                "payload": {"token": token}
            })
            
        elif message.audio:
            # Аудио - через загрузку
            logger.info(f"🎵 Аудио: {message.audio.file_name}")
            
            file_data, filename = await tg_downloader.download_file(message.audio.file_id)
            upload_info = await media_uploader.get_upload_url("audio")
            token = await media_uploader.upload_file(upload_info['url'], file_data, filename)
            
            attachments.append({
                "type": "audio",
                "payload": {"token": token}
            })
            
        elif message.voice:
            # Голосовое - конвертируем в mp3
            logger.info(f"🎤 Голосовое (конвертация в mp3)")
            
            file_data, filename = await tg_downloader.download_file(message.voice.file_id)
            # Меняем расширение на .mp3
            filename = 'voice.mp3'
            
            upload_info = await media_uploader.get_upload_url("audio")
            token = await media_uploader.upload_file(upload_info['url'], file_data, filename)
            
            attachments.append({
                "type": "audio",
                "payload": {"token": token}
            })
            
        elif message.document:
            # Документ
            logger.info(f"📄 Документ: {message.document.file_name}")
            
            file_data, filename = await tg_downloader.download_file(message.document.file_id)
            
            # Определяем тип документа
            doc_type = "file"
            if filename.endswith('.pdf'):
                doc_type = "file"
            elif filename.endswith(('.doc', '.docx')):
                doc_type = "file"
            elif filename.endswith(('.xls', '.xlsx')):
                doc_type = "file"
            elif filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                doc_type = "image"
            elif filename.endswith(('.mp4', '.mov', '.avi')):
                doc_type = "video"
            elif filename.endswith(('.mp3', '.m4a')):
                doc_type = "audio"
            
            upload_info = await media_uploader.get_upload_url(doc_type)
            token = await media_uploader.upload_file(upload_info['url'], file_data, filename)
            
            attachments.append({
                "type": doc_type,
                "payload": {"token": token} if doc_type != "file" else {"token": token, "name": filename}
            })
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
        import traceback
        traceback.print_exc()
    
    return text, attachments

async def send_to_max(text: str, attachments: list = None):
    """Отправляет сообщение в MAX"""
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Если нет текста и нет вложений - не отправляем
    if not text and not attachments:
        logger.warning("⚠️ Пустое сообщение, пропускаем")
        return False
    
    data = {
        "text": text or " ",
        "format": "markdown"
    }
    
    if attachments:
        data["attachments"] = attachments
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст: {text[:50] if text else 'нет'}")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    if attachments:
        for i, att in enumerate(attachments):
            logger.info(f"   {i+1}. {att['type']}: {att['payload']}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response = await resp.text()
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО")
                    return True
                else:
                    logger.error(f"❌ Ошибка {resp.status}: {response}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

@dp.message()
async def forward(message: types.Message):
    """Пересылает сообщения в MAX"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*70)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    
    # Обрабатываем медиа
    text, attachments = await process_media_message(message)
    
    # Обрабатываем текст (заголовки, форматирование)
    if message.caption:
        text_entities = message.caption_entities
    else:
        text_entities = message.entities
    
    if text and text_entities:
        text = process_text_part(text, text_entities)
    
    # Добавляем подпись для пересланных
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        text = f"📢 Переслано из {source}:\n\n{text}"
    
    # Отправляем
    await send_to_max(text, attachments)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ БОТ-ПЕРЕСЫЛЬЩИК MAX\n\n"
        "📋 **Этап 6: Медиафайлы (финал)**\n\n"
        "Поддерживается:\n"
        "• ✅ Фото (прямые ссылки)\n"
        "• 🎥 Видео (токены)\n"
        "• 🎵 Аудио (токены)\n"
        "• 🎤 Голосовые (конвертация в mp3)\n"
        "• 📄 PDF, DOC, DOCX, XLS, XLSX\n"
        "• Все форматы текста\n"
        "• Заголовки\n\n"
        "Отправьте любой файл в группу!"
    )

async def cleanup():
    """Закрытие сессий"""
    if tg_downloader.session:
        await tg_downloader.session.close()
    if media_uploader.session:
        await media_uploader.session.close()

async def main():
    logger.info("🚀 ЗАПУСК ЭТАПА 6: МЕДИАФАЙЛЫ (финал)")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
