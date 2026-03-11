import os
import asyncio
import logging
import aiohttp
import json
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

# === НАСТРОЙКА МАКСИМАЛЬНО ПОДРОБНОГО ЛОГИРОВАНИЯ ===
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

# Проверка наличия всех переменных
if not all([TELEGRAM_TOKEN, TELEGRAM_GROUP_ID, MAX_TOKEN, MAX_CHANNEL_ID]):
    logger.error("❌ Не все переменные окружения установлены!")
    raise ValueError("Missing environment variables")

logger.info("="*70)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID} (тип: {type(TELEGRAM_GROUP_ID)})")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}' (тип: {type(MAX_CHANNEL_ID)})")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class TelegramDownloader:
    """Класс для работы с файлами Telegram"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = None
        logger.debug(f"📦 TelegramDownloader инициализирован")
    
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            logger.debug("🔌 Сессия Telegram создана")
    
    async def get_file_path(self, file_id: str) -> str:
        """Получает путь к файлу в Telegram"""
        await self.ensure_session()
        url = f"{self.api_url}/getFile"
        
        logger.debug(f"🔍 Запрос пути файла: {file_id}")
        
        async with self.session.post(url, json={"file_id": file_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                file_path = data['result']['file_path']
                logger.debug(f"✅ Путь получен: {file_path}")
                return file_path
            else:
                error = await resp.text()
                logger.error(f"❌ Ошибка получения пути: {resp.status} - {error}")
                raise Exception(f"Ошибка получения пути файла: {resp.status}")

tg_downloader = TelegramDownloader(TELEGRAM_TOKEN)

async def send_to_max_channel(text: str, attachments: list = None, buttons: list = None):
    """Отправляет сообщение в канал MAX с максимальным логированием"""
    url = "https://platform-api.max.ru/messages"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Telegram-Forward-Bot/1.0"
    }
    
    # Формируем сообщение
    message_data = {"text": text}
    if attachments:
        message_data["attachments"] = attachments
        logger.debug(f"📎 Вложения: {json.dumps(attachments, indent=2, ensure_ascii=False)}")
    
    if buttons:
        message_data["attachments"] = message_data.get("attachments", [])
        message_data["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons}
        })
        logger.debug(f"🔘 Кнопки: {json.dumps(buttons, indent=2, ensure_ascii=False)}")
    
    # ВАЖНО: ID передаем КАК СТРОКУ, принудительно
    chat_id_str = str(MAX_CHANNEL_ID).strip()
    
    data = {
        "recipient": {
            "chat_id": chat_id_str
        },
        "message": message_data
    }
    
    logger.info("="*70)
    logger.info("📤 ОТПРАВКА В MAX КАНАЛ")
    logger.info(f"📍 URL: {url}")
    logger.info(f"🔑 Headers: {{'Authorization': '{MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}', 'Content-Type': 'application/json'}}")
    logger.info(f"👥 Recipient chat_id: '{chat_id_str}' (тип: {type(chat_id_str)})")
    logger.info(f"📝 Текст: {text[:100]}{'...' if len(text) > 100 else ''}")
    logger.info(f"📎 Вложений: {len(attachments) if attachments else 0}")
    logger.info(f"🔘 Кнопок: {len(buttons) if buttons else 0}")
    logger.info(f"📦 Полный запрос:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
    logger.info("="*70)
    
    async with aiohttp.ClientSession() as session:
        try:
            start_time = asyncio.get_event_loop().time()
            
            async with session.post(url, headers=headers, json=data) as resp:
                response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                response_text = await resp.text()
                
                logger.info(f"📥 ОТВЕТ MAX [статус: {resp.status}]")
                logger.info(f"⏱ Время ответа: {response_time:.0f}ms")
                logger.info(f"📋 Headers ответа: {dict(resp.headers)}")
                logger.info(f"📦 Тело ответа: {response_text}")
                
                if resp.status == 200:
                    logger.info("✅ УСПЕШНО ОТПРАВЛЕНО!")
                    try:
                        response_json = json.loads(response_text)
                        logger.info(f"📊 Парсинг JSON: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                    except:
                        pass
                    return True
                else:
                    logger.error(f"❌ ОШИБКА MAX: {resp.status}")
                    logger.error(f"📥 Ответ: {response_text}")
                    
                    # Анализ ошибки
                    if 'proto.payload' in response_text:
                        logger.error("🔍 ПРИЧИНА: Неизвестный получатель (Unknown recipient)")
                        logger.error("   Возможные решения:")
                        logger.error("   1️⃣ Проверьте, что бот добавлен в канал как администратор")
                        logger.error("   2️⃣ Проверьте, что у бота есть право 'Писать посты'")
                        logger.error(f"   3️⃣ Проверьте chat_id: '{chat_id_str}' - должен быть строкой")
                        logger.error("   4️⃣ Проверьте, что канал принадлежит тому же ИП")
                    return False
                    
        except aiohttp.ClientConnectorError as e:
            logger.error(f"❌ Ошибка подключения к MAX: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            logger.exception("Детальный стек ошибки:")
            return False

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
    return None

async def process_media(message: types.Message) -> list:
    """Обрабатывает медиа из сообщения"""
    attachments = []
    media_type = get_media_type(message)
    
    if not media_type:
        logger.debug("📭 Медиа не найдено")
        return attachments
    
    logger.info(f"🖼️ Обнаружен тип медиа: {media_type}")
    
    try:
        # Для фото - быстрая отправка по URL
        if media_type == 'photo':
            file_id = message.photo[-1].file_id
            logger.debug(f"📸 file_id фото: {file_id}")
            logger.debug(f"📐 Размеры: {message.photo[-1].width}x{message.photo[-1].height}")
            
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"✅ Фото обработано: {photo_url[:100]}...")
        
        # Для видео
        elif media_type == 'video':
            logger.info("🎥 Видео пока обрабатывается как ссылка")
            # Здесь можно добавить обработку видео
            pass
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
        logger.exception("Детали ошибки:")
    
    return attachments

async def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
        logger.info(f"🔘 Обнаружены inline кнопки")
        
        for row_idx, row in enumerate(message.reply_markup.inline_keyboard):
            button_row = []
            for btn_idx, btn in enumerate(row):
                if hasattr(btn, 'url') and btn.url:
                    logger.debug(f"   Кнопка {row_idx+1}.{btn_idx+1}: '{btn.text}' -> {btn.url}")
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                buttons.append(button_row)
        
        logger.info(f"✅ Найдено {len(buttons)} рядов кнопок")
    
    return buttons

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщения из Telegram в MAX"""
    
    # Проверка источника
    if message.chat.id != TELEGRAM_GROUP_ID:
        logger.debug(f"Сообщение из другого чата: {message.chat.id} (нужен: {TELEGRAM_GROUP_ID})")
        return
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info("="*70)
    
    # Базовая информация
    logger.info(f"👤 Отправитель: {message.from_user.full_name}")
    logger.info(f"🆔 ID отправителя: {message.from_user.id}")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    logger.info(f"💬 Чат ID: {message.chat.id}")
    logger.info(f"📌 Тип чата: {message.chat.type}")
    logger.info(f"🕐 Время: {message.date}")
    
    # Текст сообщения
    text = message.text or message.caption or ""
    if text:
        logger.info(f"📝 Текст: {text}")
        logger.info(f"📏 Длина: {len(text)} символов")
    else:
        logger.info("📝 Текст отсутствует")
    
    # Информация о пересылке
    if message.forward_date:
        logger.info("🔄 ЭТО ПЕРЕСЛАННОЕ СООБЩЕНИЕ")
        logger.info(f"   📅 Оригинальная дата: {message.forward_date}")
        
        if message.forward_from_chat:
            logger.info(f"   📢 Из канала: {message.forward_from_chat.title}")
            logger.info(f"   🆔 ID канала: {message.forward_from_chat.id}")
            text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
            logger.info(f"   ✅ Добавлена подпись об источнике")
            
        elif message.forward_from:
            logger.info(f"   👤 От пользователя: {message.forward_from.full_name}")
            text = f"👤 Переслано от {message.forward_from.full_name}:\n\n{text}"
            logger.info(f"   ✅ Добавлена подпись об отправителе")
    
    # Тип контента
    media_type = get_media_type(message)
    if media_type:
        logger.info(f"🖼️ Тип медиа: {media_type}")
    
    # Альбом
    if message.media_group_id:
        logger.info(f"🖼️👥 ЭТО АЛЬБОМ (группа медиа)")
        logger.info(f"   ID группы: {message.media_group_id}")
    
    # Обрабатываем медиа
    attachments = await process_media(message)
    
    # Извлекаем кнопки
    buttons = await extract_buttons(message)
    
    # Отправляем в MAX
    logger.info("="*70)
    logger.info("🚀 НАЧАЛО ОТПРАВКИ В MAX")
    
    success = await send_to_max_channel(text, attachments, buttons)
    
    if success:
        logger.info("✅ СООБЩЕНИЕ УСПЕШНО ПЕРЕСЛАНО")
    else:
        logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
    
    logger.info("="*70)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **Бот-пересыльщик MAX**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📋 **Поддерживается:**\n"
        "• Текст\n"
        "• Фото (через URL)\n"
        "• Пересланные сообщения\n"
        "• Кнопки-ссылки\n\n"
        "🔍 **Диагностика:**\n"
        "• Проверьте логи для отладки"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая команда для проверки подключения"""
    await message.answer("🔄 Тестирую подключение к MAX...")
    
    test_text = "🔄 Тестовое сообщение из диагностики"
    success = await send_to_max_channel(test_text)
    
    if success:
        await message.answer("✅ Подключение к MAX работает!")
    else:
        await message.answer("❌ Ошибка подключения к MAX. Проверьте логи.")

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    """Показывает текущие настройки"""
    debug_info = (
        f"🔧 **ТЕКУЩИЕ НАСТРОЙКИ:**\n\n"
        f"📤 TELEGRAM_GROUP_ID: `{TELEGRAM_GROUP_ID}`\n"
        f"📥 MAX_CHANNEL_ID: `{MAX_CHANNEL_ID}` (тип: {type(MAX_CHANNEL_ID)})\n"
        f"🔑 MAX_TOKEN: `{MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}`\n"
        f"🤖 TELEGRAM_TOKEN: `{TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}`\n\n"
        f"📊 **Проверка:**\n"
        f"• Бот в группе: ✅\n"
        f"• Канал ID: {MAX_CHANNEL_ID}\n"
        f"• Формат ID: {'строка' if isinstance(MAX_CHANNEL_ID, str) else 'число'}"
    )
    await message.answer(debug_info)

async def cleanup():
    """Закрытие сессий"""
    if tg_downloader.session:
        await tg_downloader.session.close()
        logger.debug("🔒 Сессия Telegram закрыта")

async def main():
    logger.info("="*70)
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА")
    logger.info("="*70)
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
    logger.info(f"🌐 MAX API URL: https://platform-api.max.ru")
    logger.info("="*70)
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    finally:
        asyncio.run(cleanup())
