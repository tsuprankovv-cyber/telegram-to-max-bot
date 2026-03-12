import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# === НАСТРОЙКА МАКСИМАЛЬНОГО ЛОГИРОВАНИЯ ===
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
    """Класс для загрузки медиа в MAX с универсальным алгоритмом"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        self.stats = {"json": 0, "xml": 0, "html": 0, "url": 0, "failed": 0}
    
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
                logger.info(f"✅ Получен URL для загрузки")
                return result
            else:
                error = await resp.text()
                logger.error(f"❌ Ошибка получения URL: {resp.status}")
                raise Exception(f"Ошибка получения URL: {resp.status}")
    
    async def upload_file_universal(self, upload_url: str, file_data: bytes, filename: str, media_type: str) -> dict:
        """
        Универсальная загрузка с перебором 4 способов
        Возвращает словарь с результатом и методом
        """
        await self.ensure_session()
        
        # Нормализуем имя файла для разных способов
        base_name = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        
        # Подготавливаем варианты имени файла для разных способов
        filenames_to_try = [
            filename,  # оригинал
            f"{base_name}.mp3",  # для аудио
            f"{base_name}.mp4",  # для видео
            f"file{ext}",  # без имени
            "audio.mp3",  # универсальное имя
            "video.mp4",
            "voice.mp3"
        ]
        
        # Определяем MIME-тип
        content_types = []
        base_type = mimetypes.guess_type(filename)[0]
        if base_type:
            content_types.append(base_type)
        
        # Добавляем варианты MIME-типов
        if media_type == "audio":
            content_types.extend(['audio/mpeg', 'audio/ogg', 'audio/wav', 'audio/mp4'])
        elif media_type == "video":
            content_types.extend(['video/mp4', 'video/quicktime', 'video/x-msvideo'])
        elif media_type == "file":
            content_types.extend(['application/pdf', 'application/msword', 
                                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
        else:
            content_types.append('application/octet-stream')
        
        # Пробуем разные комбинации имени файла и MIME-типа
        for test_filename in filenames_to_try[:3]:  # первые 3 варианта
            for content_type in content_types[:2]:  # первые 2 варианта MIME
                try:
                    logger.info(f"🔄 Попытка: {test_filename} ({content_type})")
                    
                    data = aiohttp.FormData()
                    data.add_field('file', file_data, filename=test_filename, content_type=content_type)
                    
                    async with self.session.post(upload_url, data=data) as resp:
                        response_text = await resp.text()
                        logger.info(f"📥 Статус: {resp.status}, Ответ: {response_text[:200]}")
                        
                        if resp.status == 200:
                            # СПОСОБ 1: Пробуем JSON
                            try:
                                result = json.loads(response_text)
                                if result.get('token'):
                                    logger.info(f"✅ СПОСОБ 1 (JSON) успешен: токен получен")
                                    self.stats["json"] += 1
                                    return {"token": result['token'], "method": "json", "status": "success"}
                            except:
                                pass
                            
                            # СПОСОБ 2: Пробуем XML <retval>
                            xml_match = re.search(r'<retval>(\d+)</retval>', response_text)
                            if xml_match:
                                token = xml_match.group(1)
                                logger.info(f"✅ СПОСОБ 2 (XML) успешен: токен {token}")
                                self.stats["xml"] += 1
                                return {"token": token, "method": "xml", "status": "success"}
                            
                            # СПОСОБ 3: Пробуем найти любой токен в HTML
                            html_token = re.search(r'token[=:]["\']?([a-zA-Z0-9_\-]+)["\']?', response_text)
                            if html_token:
                                token = html_token.group(1)
                                logger.info(f"✅ СПОСОБ 3 (HTML) успешен: токен {token[:20]}...")
                                self.stats["html"] += 1
                                return {"token": token, "method": "html", "status": "success"}
                            
                            # Если ничего не нашли, но статус 200
                            logger.info(f"⚠️ Статус 200, но токен не найден, сохраняем как есть")
                            self.stats["failed"] += 1
                            return {"token": response_text.strip(), "method": "raw", "status": "unknown"}
                            
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка попытки: {e}")
                    continue
        
        # СПОСОБ 4: Если всё плохо, возвращаем None (будет использована прямая ссылка)
        logger.warning(f"⚠️ Все способы загрузки не удались")
        self.stats["url"] += 1
        return {"token": None, "method": "url", "status": "failed"}

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
    """Обрабатывает медиа-сообщение с универсальным алгоритмом"""
    attachments = []
    text = message.caption or ""
    
    try:
        if message.photo:
            # Фото - всегда через URL (работает стабильно)
            photo = message.photo[-1]
            logger.info(f"🖼️ Фото: {photo.width}x{photo.height}")
            
            file_info = await tg_downloader.get_file_info(photo.file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            
        elif any([message.video, message.audio, message.voice, message.document]):
            # Определяем тип медиа
            if message.video:
                media_type = "video"
                file_id = message.video.file_id
                file_name = message.video.file_name or "video.mp4"
                logger.info(f"🎥 Видео: {file_name}")
            elif message.audio:
                media_type = "audio"
                file_id = message.audio.file_id
                file_name = message.audio.file_name or "audio.mp3"
                logger.info(f"🎵 Аудио: {file_name}")
            elif message.voice:
                media_type = "audio"
                file_id = message.voice.file_id
                file_name = "voice.mp3"  # принудительно mp3
                logger.info(f"🎤 Голосовое (как mp3)")
            elif message.document:
                # Для документов определяем тип по расширению
                file_name = message.document.file_name
                file_id = message.document.file_id
                
                if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    media_type = "image"
                elif file_name.endswith(('.mp4', '.mov', '.avi')):
                    media_type = "video"
                elif file_name.endswith(('.mp3', '.ogg', '.wav')):
                    media_type = "audio"
                else:
                    media_type = "file"
                
                logger.info(f"📄 Документ: {file_name} (как {media_type})")
            
            # Скачиваем файл
            file_data, original_filename = await tg_downloader.download_file(file_id)
            
            # Получаем URL для загрузки
            upload_info = await media_uploader.get_upload_url(media_type)
            
            # Универсальная загрузка с перебором способов
            result = await media_uploader.upload_file_universal(
                upload_info['url'], 
                file_data, 
                file_name, 
                media_type
            )
            
            # Формируем attachment
            if result["token"]:
                # Успешно получили токен
                if media_type == "file":
                    attachments.append({
                        "type": media_type,
                        "payload": {
                            "token": result["token"],
                            "name": file_name
                        }
                    })
                else:
                    attachments.append({
                        "type": media_type,
                        "payload": {"token": result["token"]}
                    })
                logger.info(f"✅ Загружено способом {result['method']}")
            else:
                # Если не получили токен, пробуем прямую ссылку
                logger.warning(f"⚠️ Не удалось получить токен, пробуем прямую ссылку")
                file_info = await tg_downloader.get_file_info(file_id)
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
                
                attachments.append({
                    "type": media_type if media_type != "file" else "file",
                    "payload": {"url": file_url} if media_type != "file" else {"url": file_url, "name": file_name}
                })
                logger.info(f"✅ Отправляем прямой ссылкой")
    
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
            payload_preview = str(att['payload'])[:100]
            logger.info(f"   {i+1}. {att['type']}: {payload_preview}")
    
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
    stats = media_uploader.stats
    await message.answer(
        "✅ БОТ-ПЕРЕСЫЛЬЩИК MAX\n\n"
        "📋 **Универсальный алгоритм загрузки**\n\n"
        f"📊 **Статистика способов:**\n"
        f"• JSON: {stats['json']}\n"
        f"• XML: {stats['xml']}\n"
        f"• HTML: {stats['html']}\n"
        f"• Прямые ссылки: {stats['url']}\n"
        f"• Ошибки: {stats['failed']}\n\n"
        "Отправьте любой файл в группу!"
    )

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    stats = media_uploader.stats
    await message.answer(
        f"📊 **СТАТИСТИКА ЗАГРУЗОК:**\n\n"
        f"✅ JSON (способ 1): {stats['json']}\n"
        f"✅ XML (способ 2): {stats['xml']}\n"
        f"✅ HTML (способ 3): {stats['html']}\n"
        f"✅ Прямые ссылки (способ 4): {stats['url']}\n"
        f"❌ Ошибки: {stats['failed']}"
    )

async def cleanup():
    """Закрытие сессий"""
    if tg_downloader.session:
        await tg_downloader.session.close()
    if media_uploader.session:
        await media_uploader.session.close()
    logger.info(f"📊 Итоговая статистика: {media_uploader.stats}")

async def main():
    logger.info("🚀 ЗАПУСК С УНИВЕРСАЛЬНЫМ АЛГОРИТМОМ")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
