import os
import asyncio
import logging
import aiohttp
import json
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from typing import List, Tuple, Optional, Dict
from datetime import datetime

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

logger.info("="*80)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === ХРАНИЛИЩЕ ДЛЯ АЛЬБОМОВ ===
albums: Dict[str, List[types.Message]] = {}
album_lock = asyncio.Lock()

# === ХРАНИЛИЩЕ ДЛЯ СООТВЕТСТВИЯ СООБЩЕНИЙ (для редактирования) ===
message_map: Dict[int, str] = {}  # telegram_message_id -> max_message_url

class TelegramDownloader:
    """Класс для получения информации о файлах из Telegram"""
    
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
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

downloader = TelegramDownloader(TELEGRAM_TOKEN)

# === ТЕКСТОВЫЕ ФУНКЦИИ ===
def format_text_with_entities(text: str, entities: list) -> str:
    """
    Применяет форматирование к тексту, проходя по entities от конца к началу
    """
    if not entities or not text:
        return text or ""
    
    # Сортируем от конца к началу
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
        elif entity.type == "code":
            replacement = f"`{fragment}`"
        elif entity.type == "pre":
            replacement = f"```\n{fragment}\n```"
        elif entity.type == "text_link":
            replacement = f"[{fragment}]({entity.url})"
        elif entity.type == "blockquote":
            replacement = f"> {fragment}"
        else:
            continue
        
        result = result[:start] + replacement + result[end:]
    
    return result

def extract_buttons(message: types.Message) -> Optional[List[List[dict]]]:
    """Извлекает кнопки-ссылки из сообщения"""
    if not message.reply_markup or not message.reply_markup.inline_keyboard:
        return None
    
    buttons = []
    for row in message.reply_markup.inline_keyboard:
        button_row = []
        for button in row:
            if button.url:
                button_row.append({
                    "type": "link",
                    "text": button.text,
                    "url": button.url
                })
        if button_row:
            buttons.append(button_row)
    
    return buttons if buttons else None

async def create_attachment(message: types.Message) -> Optional[dict]:
    """
    Универсальная функция: создаёт attachment из любого медиа через прямую ссылку
    """
    try:
        # Определяем тип и получаем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            media_type = "image"
            logger.info("🖼️ [МЕДИА] Фото")
            
        elif message.video:
            file_id = message.video.file_id
            media_type = "video"
            logger.info(f"🎥 [МЕДИА] Видео ({message.video.file_size / (1024*1024):.1f} МБ)")
            
        elif message.audio:
            file_id = message.audio.file_id
            media_type = "audio"
            logger.info(f"🎵 [МЕДИА] Аудио: {message.audio.file_name}")
            
        elif message.voice:
            file_id = message.voice.file_id
            media_type = "audio"
            logger.info("🎤 [МЕДИА] Голосовое")
            
        elif message.document:
            file_name = message.document.file_name
            file_id = message.document.file_id
            
            # Определяем тип по расширению
            ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                media_type = "image"
                logger.info(f"🖼️ [МЕДИА] Изображение: {file_name}")
            elif ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
                media_type = "video"
                logger.info(f"🎥 [МЕДИА] Видео: {file_name}")
            elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac']:
                media_type = "audio"
                logger.info(f"🎵 [МЕДИА] Аудио: {file_name}")
            else:
                media_type = "file"
                logger.info(f"📄 [МЕДИА] Документ: {file_name}")
        else:
            return None
        
        # Получаем прямую ссылку на файл
        file_info = await downloader.get_file_info(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['file_path']}"
        
        # Возвращаем attachment с ссылкой
        if media_type == "file":
            return {
                "type": media_type,
                "payload": {
                    "url": file_url,
                    "name": message.document.file_name
                }
            }
        else:
            return {
                "type": media_type,
                "payload": {"url": file_url}
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания attachment: {e}")
        return None

async def send_to_max(text: str, attachments: List[dict] = None, buttons: List[List[dict]] = None) -> Optional[str]:
    """
    Отправляет сообщение в MAX и возвращает URL сообщения
    """
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text or " ",
        "format": "markdown"
    }
    
    if attachments:
        data["attachments"] = attachments
    
    if buttons:
        data["attachments"] = data.get("attachments", [])
        data["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
    
    logger.info("="*80)
    logger.info(f"📤 ОТПРАВКА В MAX")
    logger.info(f"📝 Текст: {text[:100] if text else 'нет'}")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    logger.info(f"🔘 Кнопок: {len(buttons) if buttons else 0}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                response = await resp.json()
                
                if resp.status == 200:
                    message_url = response.get('message', {}).get('url')
                    logger.info(f"✅ УСПЕШНО: {message_url}")
                    return message_url
                else:
                    logger.error(f"❌ Ошибка {resp.status}: {response}")
                    return None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None

async def process_album(album_id: str, messages: List[types.Message]):
    """Обрабатывает альбом из нескольких сообщений"""
    logger.info(f"📸 [АЛЬБОМ] Обработка {len(messages)} сообщений")
    
    all_attachments = []
    caption = messages[0].caption or ""
    caption_entities = messages[0].caption_entities
    
    for msg in messages:
        attachment = await create_attachment(msg)
        if attachment:
            all_attachments.append(attachment)
    
    if all_attachments:
        # Форматируем подпись
        formatted_text = format_text_with_entities(caption, caption_entities) if caption_entities else caption
        
        # Добавляем подпись о пересылке
        if messages[0].forward_date and messages[0].forward_from_chat:
            source = messages[0].forward_from_chat.title
            formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
        
        # Отправляем
        message_url = await send_to_max(formatted_text, all_attachments)
        
        # Сохраняем соответствие для редактирования
        for msg in messages:
            message_map[msg.message_id] = message_url

@dp.message()
async def forward(message: types.Message):
    """Основной обработчик"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ID: {message.message_id}")
    logger.info(f"📦 Тип: {message.content_type}")
    
    # Проверяем, является ли сообщение частью альбома
    if message.media_group_id:
        album_id = message.media_group_id
        logger.info(f"📸 [АЛЬБОМ] Часть альбома {album_id}")
        
        async with album_lock:
            if album_id not in albums:
                albums[album_id] = []
                # Запускаем обработку через 2 секунды
                asyncio.create_task(process_album_after_delay(album_id))
            
            albums[album_id].append(message)
            logger.info(f"📸 [АЛЬБОМ] В альбоме {len(albums[album_id])} сообщений")
        
        return
    
    # Обработка одиночных сообщений
    attachments = []
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    
    # Создаём attachment если есть медиа
    if message.photo or message.video or message.audio or message.voice or message.document:
        attachment = await create_attachment(message)
        if attachment:
            attachments.append(attachment)
    
    # Извлекаем кнопки
    buttons = extract_buttons(message)
    
    # Форматируем текст
    formatted_text = format_text_with_entities(text, entities) if entities else text
    
    # Добавляем подпись о пересылке
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
    
    # Отправляем
    if attachments or formatted_text:
        message_url = await send_to_max(formatted_text, attachments, buttons)
        if message_url:
            message_map[message.message_id] = message_url

async def process_album_after_delay(album_id: str, delay: int = 2):
    """Обрабатывает альбом после небольшой задержки"""
    await asyncio.sleep(delay)
    
    async with album_lock:
        if album_id in albums:
            messages = albums.pop(album_id)
            await process_album(album_id, messages)

@dp.edited_message()
async def edit_message(message: types.Message):
    """Обработчик редактирования сообщений"""
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    if message.message_id not in message_map:
        logger.warning(f"⚠️ Нет информации об оригинальном сообщении {message.message_id}")
        return
    
    max_url = message_map[message.message_id]
    logger.info(f"✏️ Редактирование сообщения {message.message_id} -> {max_url}")
    
    # Получаем новый текст и форматирование
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    formatted_text = format_text_with_entities(text, entities) if entities else text
    
    # Отправляем PUT-запрос на обновление
    url = f"https://platform-api.max.ru/messages?message_id={max_url.split('/')[-1]}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": formatted_text,
        "format": "markdown"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=data) as resp:
            if resp.status == 200:
                logger.info("✅ Сообщение обновлено")
            else:
                logger.error(f"❌ Ошибка редактирования: {resp.status}")

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "✅ **MAX ПЕРЕСЫЛЬЩИК (ВЕРСИЯ 2.0 - ПРЯМЫЕ ССЫЛКИ)**\n\n"
        "📋 **ПОДДЕРЖИВАЕТСЯ:**\n"
        "• 📝 Текст с полным форматированием\n"
        "• 🖼️ Фото (прямые ссылки)\n"
        "• 🎥 Видео любого размера (прямые ссылки)\n"
        "• 🎵 Аудио (прямые ссылки)\n"
        "• 🎤 Голосовые\n"
        "• 📄 PDF, DOC, XLS\n"
        "• 🔗 Кнопки-ссылки\n"
        "• 📸 Альбомы (фото+видео)\n"
        "• ✏️ Редактирование сообщений\n\n"
        "✅ **ПОЛНАЯ ИДЕНТИЧНОСТЬ ПОСТОВ!**"
    )

async def cleanup():
    if downloader.session:
        await downloader.session.close()

async def main():
    logger.info("🚀 ЗАПУСК НОВОЙ ВЕРСИИ (ПРЯМЫЕ ССЫЛКИ)")
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Стоп")
    finally:
        asyncio.run(cleanup())
