import os
import asyncio
import logging
import aiohttp
import json
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

class TelegramDownloader:
    """Класс для получения информации о файлах из Telegram"""
    
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']['file_path']
            else:
                error = await resp.text()
                raise Exception(f"Ошибка получения пути: {resp.status}")

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

async def get_file_url(file_id: str) -> str:
    """Получает прямую ссылку на файл в Telegram"""
    file_path = await tg_downloader.get_file_path(file_id)
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

async def process_media_message(message: types.Message) -> tuple[str, list]:
    """Обрабатывает медиа-сообщение, используя прямые ссылки"""
    attachments = []
    text = message.caption or ""
    
    try:
        if message.photo:
            # Фото - прямая ссылка
            photo = message.photo[-1]
            logger.info(f"🖼️ Фото: {photo.width}x{photo.height}")
            
            file_url = await get_file_url(photo.file_id)
            attachments.append({
                "type": "image",
                "payload": {"url": file_url}
            })
            
        elif message.video:
            # Видео - прямая ссылка
            logger.info(f"🎥 Видео: {message.video.file_name or 'без названия'}")
            
            file_url = await get_file_url(message.video.file_id)
            attachments.append({
                "type": "video",
                "payload": {"url": file_url}
            })
            
        elif message.audio:
            # Аудио - прямая ссылка
            logger.info(f"🎵 Аудио: {message.audio.file_name}")
            
            file_url = await get_file_url(message.audio.file_id)
            attachments.append({
                "type": "audio",
                "payload": {"url": file_url}
            })
            
        elif message.voice:
            # Голосовое - прямая ссылка
            logger.info(f"🎤 Голосовое")
            
            file_url = await get_file_url(message.voice.file_id)
            attachments.append({
                "type": "audio",
                "payload": {"url": file_url}
            })
            
        elif message.document:
            # Документ - прямая ссылка
            logger.info(f"📄 Документ: {message.document.file_name}")
            
            file_url = await get_file_url(message.document.file_id)
            attachments.append({
                "type": "file",
                "payload": {
                    "url": file_url,
                    "name": message.document.file_name
                }
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
        "📋 **Этап 6: Медиафайлы (прямые ссылки)**\n\n"
        "Поддерживается:\n"
        "• Фото с подписями\n"
        "• Видео (прямые ссылки)\n"
        "• Аудио (прямые ссылки)\n"
        "• Голосовые (прямые ссылки)\n"
        "• Документы (прямые ссылки)\n"
        "• Все форматы текста\n"
        "• Заголовки\n\n"
        "Отправьте любой файл в группу!"
    )

async def cleanup():
    """Закрытие сессий"""
    if tg_downloader.session:
        await tg_downloader.session.close()

async def main():
    logger.info("🚀 ЗАПУСК ЭТАПА 6: МЕДИАФАЙЛЫ (прямые ссылки)")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
