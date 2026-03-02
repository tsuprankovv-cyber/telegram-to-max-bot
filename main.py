import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from maxapi import Bot as MaxBot

# === НАСТРОЙКА ПОДРОБНОГО ЛОГИРОВАНИЯ ===
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

# Проверка наличия всех переменных
if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

telegram_bot = Bot(token=TELEGRAM_TOKEN)
max_bot = MaxBot(token=MAX_TOKEN)
dp = Dispatcher()

async def download_file(file_id: str) -> str:
    """Скачивает файл из Telegram и возвращает ссылку на него"""
    try:
        logger.info(f"📥 Начинаем скачивание файла: {file_id}")
        file = await telegram_bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        logger.info(f"✅ Файл успешно скачан: {file_url}")
        logger.info(f"   Путь к файлу: {file.file_path}")
        logger.info(f"   Размер файла: {file.file_size if hasattr(file, 'file_size') else 'неизвестно'} байт")
        return file_url
    except Exception as e:
        logger.error(f"❌ Ошибка при скачивании файла {file_id}: {e}")
        logger.exception("Детали ошибки:")
        raise

def extract_buttons(message: types.Message):
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        logger.info(f"🔘 Обнаружены кнопки: {len(message.reply_markup.inline_keyboard)} рядов")
        for row_idx, row in enumerate(message.reply_markup.inline_keyboard):
            button_row = []
            for button in row:
                if button.url:
                    button_row.append({
                        "text": button.text,
                        "url": button.url
                    })
                    logger.info(f"   Кнопка {row_idx+1}: '{button.text}' -> {button.url}")
            if button_row:
                buttons.append(button_row)
        logger.info(f"✅ Всего кнопок для отправки: {sum(len(row) for row in buttons)}")
    return buttons

@dp.message()
async def forward_to_max(message: types.Message):
    """Основной обработчик сообщений"""
    
    # === ПРОВЕРКА ИСТОЧНИКА ===
    if message.chat.id != TELEGRAM_GROUP_ID:
        logger.debug(f"Сообщение из другого чата: {message.chat.id} (нужен: {TELEGRAM_GROUP_ID})")
        return
    
    # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ СООБЩЕНИЯ ===
    logger.info("="*70)
    logger.info("📨 ПОЛУЧЕНО НОВОЕ СООБЩЕНИЕ ДЛЯ ПЕРЕСЫЛКИ")
    logger.info("="*70)
    
    # Базовая информация
    logger.info(f"🆔 ID сообщения: {message.message_id}")
    logger.info(f"👤 Отправитель: {message.from_user.full_name} (ID: {message.from_user.id})")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    logger.info(f"📱 Username: @{message.from_user.username if message.from_user.username else 'нет'}")
    logger.info(f"💬 Чат: {message.chat.title if message.chat.title else 'Личка'} (ID: {message.chat.id})")
    logger.info(f"📌 Тип чата: {message.chat.type}")
    logger.info(f"🕐 Время отправки: {message.date}")
    
    # === ИНФОРМАЦИЯ О ПЕРЕСЫЛКЕ (самое важное для нашей проблемы) ===
    if message.forward_date:
        logger.info("🔄 ЭТО ПЕРЕСЛАННОЕ СООБЩЕНИЕ:")
        logger.info(f"  📅 Оригинальная дата: {message.forward_date}")
        
        if message.forward_from:
            logger.info(f"  👤 От пользователя: {message.forward_from.full_name}")
            logger.info(f"  🆔 ID пользователя: {message.forward_from.id}")
            logger.info(f"  📱 Username: @{message.forward_from.username if message.forward_from.username else 'нет'}")
            
        if message.forward_from_chat:
            logger.info(f"  📢 Из канала/чата: {message.forward_from_chat.title}")
            logger.info(f"  🆔 ID канала: {message.forward_from_chat.id}")
            logger.info(f"  📢 Username канала: @{message.forward_from_chat.username if message.forward_from_chat.username else 'нет'}")
            
        if message.forward_sender_name:
            logger.info(f"  🏷 Скрытое имя: {message.forward_sender_name}")
            
        if message.forward_signature:
            logger.info(f"  ✍️ Подпись: {message.forward_signature}")
    else:
        logger.info("📨 Обычное сообщение (не пересланное)")
    
    # === ТИП КОНТЕНТА ===
    text = message.text or message.caption or ''
    if text:
        logger.info(f"📝 Текст/подпись: {text[:200]}{'...' if len(text) > 200 else ''}")
    
    # Фото
    if message.photo:
        logger.info(f"🖼 ОБНАРУЖЕНО ФОТО:")
        logger.info(f"   Количество версий: {len(message.photo)}")
        for i, photo in enumerate(message.photo):
            logger.info(f"   Версия {i+1}: {photo.width}x{photo.height}, file_id: {photo.file_id[:20]}...")
        main_photo = message.photo[-1]
        logger.info(f"   ✅ Используем версию: {main_photo.width}x{main_photo.height}")
        logger.info(f"   🆔 file_id: {main_photo.file_id}")
    
    # Видео
    elif message.video:
        logger.info(f"🎥 ОБНАРУЖЕНО ВИДЕО:")
        logger.info(f"   Размер: {message.video.width}x{message.video.height}")
        logger.info(f"   Длительность: {message.video.duration} сек")
        logger.info(f"   🆔 file_id: {message.video.file_id}")
        logger.info(f"   📁 MIME тип: {message.video.mime_type}")
        logger.info(f"   💾 Размер файла: {message.video.file_size} байт")
    
    # Голосовое
    elif message.voice:
        logger.info(f"🎤 ОБНАРУЖЕНО ГОЛОСОВОЕ:")
        logger.info(f"   Длительность: {message.voice.duration} сек")
        logger.info(f"   🆔 file_id: {message.voice.file_id}")
    
    # Документ
    elif message.document:
        logger.info(f"📄 ОБНАРУЖЕН ДОКУМЕНТ:")
        logger.info(f"   Имя файла: {message.document.file_name}")
        logger.info(f"   🆔 file_id: {message.document.file_id}")
        logger.info(f"   📁 MIME тип: {message.document.mime_type}")
        logger.info(f"   💾 Размер: {message.document.file_size} байт")
    
    # Текст
    elif message.text:
        logger.info(f"📝 ОБНАРУЖЕН ТЕКСТ")
    
    # Другие типы
    elif message.sticker:
        logger.info(f"🎯 ОБНАРУЖЕН СТИКЕР")
    elif message.contact:
        logger.info(f"👤 ОБНАРУЖЕН КОНТАКТ")
    elif message.location:
        logger.info(f"📍 ОБНАРУЖЕНА ЛОКАЦИЯ")
    else:
        logger.warning(f"⚠️ НЕИЗВЕСТНЫЙ ТИП СООБЩЕНИЯ")
    
    # Альбом
    if message.media_group_id:
        logger.info(f"🖼👥 ЭТО АЛЬБОМ (группа медиа)")
        logger.info(f"   ID группы: {message.media_group_id}")
    
    # Кнопки
    buttons = extract_buttons(message)
    
    logger.info("="*70)
    
    # === НАЧАЛО ПЕРЕСЫЛКИ ===
    try:
        # Формируем текст с информацией об источнике (если нужно)
        final_text = text
        if message.forward_from_chat and text:
            source_title = message.forward_from_chat.title or "канала"
            final_text = f"📢 Переслано из {source_title}:\n\n{text}"
            logger.info(f"📝 Добавлена информация об источнике: {source_title}")
        elif message.forward_from and text:
            source_name = message.forward_from.full_name or "пользователя"
            final_text = f"👤 Переслано от {source_name}:\n\n{text}"
            logger.info(f"📝 Добавлена информация об отправителе: {source_name}")
        
        # Отправка в зависимости от типа
        if message.photo:
            logger.info("🔄 НАЧИНАЕМ ПЕРЕСЫЛКУ ФОТО...")
            photo = message.photo[-1]
            photo_url = await download_file(photo.file_id)
            
            logger.info(f"📤 Отправляем фото в MAX (канал: {MAX_CHANNEL_ID})")
            if buttons:
                result = await max_bot.send_photo(
                    chat_id=MAX_CHANNEL_ID,
                    photo=photo_url,
                    caption=final_text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                result = await max_bot.send_photo(
                    chat_id=MAX_CHANNEL_ID,
                    photo=photo_url,
                    caption=final_text
                )
            logger.info(f"✅ ФОТО УСПЕШНО ПЕРЕСЛАНО!")
            logger.info(f"   Ответ от MAX API: {result}")
            
        elif message.video:
            logger.info("🔄 НАЧИНАЕМ ПЕРЕСЫЛКУ ВИДЕО...")
            video_url = await download_file(message.video.file_id)
            
            logger.info(f"📤 Отправляем видео в MAX (канал: {MAX_CHANNEL_ID})")
            if buttons:
                result = await max_bot.send_video(
                    chat_id=MAX_CHANNEL_ID,
                    video=video_url,
                    caption=final_text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                result = await max_bot.send_video(
                    chat_id=MAX_CHANNEL_ID,
                    video=video_url,
                    caption=final_text
                )
            logger.info(f"✅ ВИДЕО УСПЕШНО ПЕРЕСЛАНО!")
            logger.info(f"   Ответ от MAX API: {result}")
            
        elif message.voice:
            logger.info("🔄 НАЧИНАЕМ ПЕРЕСЫЛКУ ГОЛОСОВОГО...")
            voice_url = await download_file(message.voice.file_id)
            
            logger.info(f"📤 Отправляем голосовое в MAX (канал: {MAX_CHANNEL_ID})")
            if buttons:
                result = await max_bot.send_voice(
                    chat_id=MAX_CHANNEL_ID,
                    voice=voice_url,
                    caption=final_text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                result = await max_bot.send_voice(
                    chat_id=MAX_CHANNEL_ID,
                    voice=voice_url,
                    caption=final_text
                )
            logger.info(f"✅ ГОЛОСОВОЕ УСПЕШНО ПЕРЕСЛАНО!")
            logger.info(f"   Ответ от MAX API: {result}")
            
        elif message.document:
            logger.info("🔄 НАЧИНАЕМ ПЕРЕСЫЛКУ ДОКУМЕНТА...")
            doc_url = await download_file(message.document.file_id)
            
            logger.info(f"📤 Отправляем документ в MAX (канал: {MAX_CHANNEL_ID})")
            if buttons:
                result = await max_bot.send_document(
                    chat_id=MAX_CHANNEL_ID,
                    document=doc_url,
                    caption=final_text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                result = await max_bot.send_document(
                    chat_id=MAX_CHANNEL_ID,
                    document=doc_url,
                    caption=final_text
                )
            logger.info(f"✅ ДОКУМЕНТ УСПЕШНО ПЕРЕСЛАН!")
            logger.info(f"   Ответ от MAX API: {result}")
            
        elif message.text:
            logger.info("🔄 НАЧИНАЕМ ПЕРЕСЫЛКУ ТЕКСТА...")
            logger.info(f"📤 Отправляем текст в MAX (канал: {MAX_CHANNEL_ID})")
            logger.info(f"   Текст: {final_text[:100]}{'...' if len(final_text) > 100 else ''}")
            
            if buttons:
                result = await max_bot.send_message(
                    chat_id=MAX_CHANNEL_ID,
                    text=final_text,
                    reply_markup={"inline_keyboard": buttons}
                )
            else:
                result = await max_bot.send_message(
                    chat_id=MAX_CHANNEL_ID,
                    text=final_text
                )
            logger.info(f"✅ ТЕКСТ УСПЕШНО ПЕРЕСЛАН!")
            logger.info(f"   Ответ от MAX API: {result}")
            
        else:
            logger.warning(f"⚠️ Тип сообщения не поддерживается для пересылки")
            
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ПЕРЕСЫЛКЕ: {e}")
        logger.exception("Детальный стек ошибки:")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "✅ Бот-пересыльщик запущен в ТЕСТОВОМ режиме!\n\n"
        f"📤 Откуда: группа с ID {TELEGRAM_GROUP_ID}\n"
        f"📥 Куда: канал MAX с ID {MAX_CHANNEL_ID}\n\n"
        "📋 Подробное логирование включено.\n"
        "Отправьте тестовые сообщения в группу."
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Команда для проверки связи с MAX"""
    await message.answer("🔄 Проверяю подключение к MAX API...")
    try:
        # Отправляем тестовое сообщение в MAX
        result = await max_bot.send_message(
            chat_id=MAX_CHANNEL_ID,
            text="🔄 Тестовое сообщение от бота-пересыльщика"
        )
        await message.answer(f"✅ Подключение к MAX работает! Ответ: {result}")
    except Exception as e:
        await message.answer(f"❌ Ошибка подключения к MAX: {e}")

async def main():
    """Запуск бота"""
    logger.info("="*70)
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (ТЕСТОВЫЙ РЕЖИМ)")
    logger.info("="*70)
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...")
    logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...")
    logger.info("="*70)
    
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
