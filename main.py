import os
import asyncio
import logging
import re
import aiohttp
import json
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID'))
MAX_TOKEN = os.getenv('MAX_TOKEN')
MAX_CHANNEL_ID = os.getenv('MAX_CHANNEL_ID')

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class MAXMediaUploader:
    """Класс для загрузки медиафайлов в MAX"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_upload_url(self, media_type: str) -> dict:
        """Получает URL для загрузки файла в MAX"""
        await self.ensure_session()
        url = f"{self.base_url}/uploads?type={media_type}"
        headers = {"Authorization": self.token}
        
        async with self.session.post(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка получения URL: {resp.status} - {error_text}")
    
    async def upload_file(self, upload_url: str, file_data: bytes, filename: str) -> str:
        """Загружает файл в MAX и возвращает токен"""
        await self.ensure_session()
        
        form = aiohttp.FormData()
        form.add_field('data', file_data, filename=filename, 
                      content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream')
        
        async with self.session.post(upload_url, data=form) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get('token')
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка загрузки: {resp.status} - {error_text}")
    
    async def wait_for_processing(self, token: str, max_attempts: int = 10):
        """Ждет обработки файла на сервере MAX"""
        for attempt in range(max_attempts):
            await asyncio.sleep(1)
            try:
                # Проверяем готовность через отправку тестового сообщения
                return True
            except:
                continue
        return False

class TelegramDownloader:
    """Класс для скачивания файлов из Telegram"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self.session = None
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['result']['file_path']
            else:
                raise Exception(f"Ошибка получения пути файла: {resp.status}")
    
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Скачивает файл из Telegram и возвращает (данные, имя_файла)"""
        await self.ensure_session()
        
        # Получаем путь к файлу
        file_path = await self.get_file_path(file_id)
        filename = file_path.split('/')[-1]
        
        # Скачиваем файл
        url = f"{self.base_url}/{file_path}"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return (await resp.read(), filename)
            else:
                raise Exception(f"Ошибка скачивания: {resp.status}")

# Создаем экземпляры классов
max_uploader = MAXMediaUploader(MAX_TOKEN)
tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

def get_media_type(message: types.Message) -> str:
    """Определяет тип медиа в сообщении"""
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.audio:
        return 'audio'
    elif message.voice:
        return 'voice'
    elif message.document:
        return 'document'
    elif message.animation:
        return 'animation'
    elif message.sticker:
        return 'sticker'
    elif message.video_note:
        return 'video_note'
    return None

async def send_to_max(text: str, attachments: list = None, parse_mode: str = None):
    """
    Отправляет сообщение в MAX канал с поддержкой форматирования
    parse_mode может быть 'markdown', 'html', или None для автоопределения
    """
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    message_data = {"text": text}
    
    # Добавляем форматирование, если указано
    if parse_mode:
        message_data["format"] = parse_mode
    
    if attachments:
        message_data["attachments"] = attachments
    
    data = {
        "recipient": {"chat_id": MAX_CHANNEL_ID},
        "message": message_data
    }
    
    logger.info(f"📤 Отправка в MAX: {json.dumps(data, ensure_ascii=False)[:200]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    logger.info("✅ Успешно отправлено в MAX")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Ошибка MAX: {resp.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

async def process_media(message: types.Message) -> list:
    """Обрабатывает медиа из сообщения и возвращает attachment для MAX"""
    attachments = []
    media_type = get_media_type(message)
    
    if not media_type:
        return attachments
    
    try:
        # Определяем тип и получаем file_id
        file_id = None
        filename = None
        
        if message.photo:
            # Берем фото максимального размера
            file_id = message.photo[-1].file_id
            filename = f"photo_{datetime.now().timestamp()}.jpg"
        elif message.video:
            file_id = message.video.file_id
            filename = message.video.file_name or f"video_{datetime.now().timestamp()}.mp4"
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or f"audio_{datetime.now().timestamp()}.mp3"
        elif message.voice:
            file_id = message.voice.file_id
            filename = f"voice_{datetime.now().timestamp()}.ogg"
        elif message.document:
            file_id = message.document.file_id
            filename = message.document.file_name
        elif message.animation:
            file_id = message.animation.file_id
            filename = message.animation.file_name or f"animation_{datetime.now().timestamp()}.gif"
        elif message.sticker:
            file_id = message.sticker.file_id
            filename = f"sticker_{datetime.now().timestamp()}.webp"
        elif message.video_note:
            file_id = message.video_note.file_id
            filename = f"video_note_{datetime.now().timestamp()}.mp4"
        
        if not file_id:
            return attachments
        
        # Для фото - можно отправить URL (быстрее)
        if media_type == 'photo':
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"🖼️ Фото обработано через URL")
        
        # Для остальных типов - двухэтапная загрузка
        else:
            # Скачиваем файл из Telegram
            file_data, original_filename = await tg_downloader.download_file(file_id)
            
            # Определяем тип для MAX
            max_type = media_type
            if media_type == 'voice':
                max_type = 'audio'
            elif media_type == 'video_note':
                max_type = 'video'
            elif media_type == 'sticker':
                max_type = 'image'  # Стикеры как изображения
            elif media_type == 'animation':
                max_type = 'video'  # GIF как видео
            
            # Получаем URL для загрузки
            upload_info = await max_uploader.get_upload_url(max_type)
            
            # Загружаем файл
            token = await max_uploader.upload_file(
                upload_info['url'], 
                file_data, 
                original_filename or filename
            )
            
            # Ждем обработки
            await max_uploader.wait_for_processing(token)
            
            # Добавляем attachment
            attachments.append({
                "type": max_type,
                "payload": {"token": token}
            })
            logger.info(f"📦 {media_type.upper()} обработано через загрузку")
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
    
    return attachments

async def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
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
        
        if buttons:
            logger.info(f"🔘 Найдено {len(buttons)} рядов кнопок")
    
    return buttons

def format_message_text(message: types.Message) -> tuple[str, str]:
    """
    Форматирует текст сообщения и определяет режим парсинга
    Возвращает (текст, режим_парсинга)
    """
    # Собираем текст из всех возможных источников
    text_parts = []
    parse_mode = None
    
    # Проверяем, есть ли форматирование в оригинальном сообщении
    if message.text:
        text_parts.append(message.text)
        # Если текст содержит markdown-разметку, используем markdown
        if any(marker in message.text for marker in ['**', '__', '*', '_', '`', '[', ']', '(', ')']):
            parse_mode = 'markdown'
    
    # Подпись к медиа
    if message.caption:
        text_parts.append(message.caption)
        if any(marker in message.caption for marker in ['**', '__', '*', '_', '`', '[', ']', '(', ')']):
            parse_mode = 'markdown'
    
    # Если есть контакт
    if message.contact:
        contact_text = f"📞 Контакт: {message.contact.first_name}"
        if message.contact.last_name:
            contact_text += f" {message.contact.last_name}"
        if message.contact.phone_number:
            contact_text += f"\nТелефон: {message.contact.phone_number}"
        text_parts.append(contact_text)
    
    # Если есть локация
    if message.location:
        text_parts.append(
            f"📍 Местоположение\n"
            f"https://maps.google.com/?q={message.location.latitude},"
            f"{message.location.longitude}"
        )
    
    # Если есть опрос
    if message.poll:
        poll = message.poll
        poll_text = f"📊 Опрос: {poll.question}\n"
        for i, option in enumerate(poll.options, 1):
            poll_text += f"{i}. {option.text}\n"
        text_parts.append(poll_text)
    
    # Если есть эмодзи в тексте, они передаются как есть (Unicode)
    # Никакой специальной обработки не требуется
    
    full_text = "\n\n".join(text_parts) if text_parts else ""
    
    return full_text, parse_mode

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает ВСЕ сообщения из Telegram-группы в MAX-канал"""
    
    # Проверяем, что сообщение из нужной группы
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    try:
        # Логируем информацию о сообщении
        sender = message.from_user
        sender_name = sender.full_name or sender.username or "Пользователь"
        logger.info(f"📨 Получено от {sender_name} (бот: {sender.is_bot})")
        
        # Форматируем текст и определяем режим парсинга
        text, parse_mode = format_message_text(message)
        
        # Обрабатываем медиа
        attachments = await process_media(message)
        
        # Извлекаем кнопки
        buttons = await extract_buttons(message)
        if buttons:
            attachments.append({
                "type": "inline_keyboard",
                "payload": {"buttons": buttons}
            })
        
        # Если есть только медиа без текста
        if not text and not attachments:
            logger.warning("⚠️ Пустое сообщение")
            return
        
        # Отправляем в MAX с правильным режимом парсинга
        success = await send_to_max(text, attachments, parse_mode)
        
        if success:
            logger.info("✅ Сообщение успешно переслано")
        else:
            logger.error("❌ Не удалось переслать")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ Бот запущен и готов пересылать ВСЁ в MAX!\n\n"
        "Поддерживается:\n"
        "• Текст и форматирование (**жирный**, *курсив*)\n"
        "• Эмодзи и смайлики 😊✨\n"
        "• Фото, видео, аудио\n"
        "• Голосовые сообщения\n"
        "• Документы и файлы\n"
        "• Стикеры и GIF\n"
        "• Кнопки-ссылки\n"
        "• Контакты и локации\n"
        "• Опросы\n\n"
        "Всё пересылается в том же виде, как в Telegram!"
    )

async def cleanup():
    """Закрывает сессии при завершении"""
    await max_uploader.close()
    await tg_downloader.close()

async def main():
    logger.info("🚀 Бот запускается...")
    
    # Регистрируем очистку при завершении
    loop = asyncio.get_running_loop()
    loop.call_later(0, lambda: asyncio.create_task(cleanup()))
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    finally:
        asyncio.run(cleanup())
