import os
import asyncio
import logging
import aiohttp
import json
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
    """Отправляет сообщение в канал MAX"""
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
    
    # ВАЖНО: ID передаем КАК СТРОКУ
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
                    return True
                else:
                    logger.error(f"❌ ОШИБКА MAX: {resp.status}")
                    logger.error(f"📥 Ответ: {response_text}")
                    
                    if 'proto.payload' in response_text:
                        logger.error("🔍 ПРИЧИНА: Неизвестный получатель (Unknown recipient)")
                        logger.error("   Возможные решения:")
                        logger.error("   1️⃣ Проверьте, что бот добавлен в канал как администратор")
                        logger.error("   2️⃣ Проверьте, что у бота есть право 'Писать посты'")
                        logger.error("   3️⃣ Проверьте, что канал принадлежит тому же ИП")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
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
    return None

async def process_media(message: types.Message) -> list:
    """Обрабатывает медиа из сообщения"""
    attachments = []
    media_type = get_media_type(message)
    
    if not media_type:
        return attachments
    
    try:
        # Для фото - отправка по URL
        if media_type == 'photo':
            file_id = message.photo[-1].file_id
            file_path = await tg_downloader.get_file_path(file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            
            attachments.append({
                "type": "image",
                "payload": {"url": photo_url}
            })
            logger.info(f"🖼️ Фото обработано")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки медиа: {e}")
    
    return attachments

async def extract_buttons(message: types.Message) -> list:
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row_idx, row in enumerate(message.reply_markup.inline_keyboard):
            button_row = []
            for btn_idx, btn in enumerate(row):
                if hasattr(btn, 'url') and btn.url:
                    button_row.append({
                        "type": "link",
                        "text": btn.text,
                        "url": btn.url
                    })
            if button_row:
                buttons.append(button_row)
        
        logger.info(f"🔘 Найдено {len(buttons)} рядов кнопок")
    
    return buttons

# === ДИАГНОСТИЧЕСКИЕ КОМАНДЫ ДЛЯ MAX ===

@dp.message(Command("max_diag"))
async def cmd_max_diagnostic(message: types.Message):
    """Полная диагностика подключения к MAX"""
    await message.answer("🔍 **ЗАПУСК ДИАГНОСТИКИ MAX**\n\n🔄 Проверяю подключение...")
    
    results = []
    results.append("📊 **РЕЗУЛЬТАТЫ ДИАГНОСТИКИ:**\n")
    
    # 1. Проверка токена (получение информации о боте)
    try:
        url = "https://platform-api.max.ru/me"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results.append("✅ **Токен**: работает")
                    results.append(f"   • Имя бота: {data.get('name', 'неизвестно')}")
                    results.append(f"   • ID бота: {data.get('user_id', 'неизвестно')}")
                    results.append(f"   • Username: @{data.get('username', 'нет')}")
                    
                    # Сохраняем ID бота для проверки
                    bot_id = data.get('user_id')
                else:
                    error = await resp.text()
                    results.append(f"❌ **Токен**: ошибка {resp.status}")
                    results.append(f"   • {error}")
    except Exception as e:
        results.append(f"❌ **Токен**: {str(e)}")
    
    # 2. Проверка доступа к каналу
    try:
        url = f"https://platform-api.max.ru/chats/{MAX_CHANNEL_ID}"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results.append(f"\n✅ **Канал**: доступен")
                    results.append(f"   • Название: {data.get('title', 'неизвестно')}")
                    results.append(f"   • ID канала: `{data.get('chat_id')}`")
                    results.append(f"   • Тип: {data.get('type', 'неизвестно')}")
                    results.append(f"   • Статус: {data.get('status', 'неизвестно')}")
                    results.append(f"   • Участников: {data.get('participants_count', 0)}")
                    results.append(f"   • Владелец: `{data.get('owner_id', 'неизвестно')}`")
                    
                    # Проверяем, совпадает ли владелец с вашим ID
                    owner_id = data.get('owner_id')
                    if owner_id:
                        results.append(f"   • Владелец {'✅ СОВПАДАЕТ' if str(owner_id) == '11814602' else '❌ НЕ СОВПАДАЕТ'} с вашим ID (11814602)")
                else:
                    results.append(f"\n❌ **Канал**: ошибка {resp.status}")
    except Exception as e:
        results.append(f"\n❌ **Канал**: {str(e)}")
    
    # 3. Проверка прав бота в канале
    try:
        url = f"https://platform-api.max.ru/chats/{MAX_CHANNEL_ID}"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Пытаемся получить информацию о правах
                    results.append(f"\n👥 **Права бота в канале:**")
                    
                    # Проверяем, может ли бот отправлять сообщения
                    if data.get('my_permissions'):
                        permissions = data.get('my_permissions', {})
                        can_send = permissions.get('send_messages', False)
                        results.append(f"   • Право отправки: {'✅ Есть' if can_send else '❌ НЕТ'}")
                    else:
                        # Если нет информации о правах, пробуем другой метод
                        url_admins = f"https://platform-api.max.ru/chats/{MAX_CHANNEL_ID}/members/admins"
                        async with session.get(url_admins, headers=headers) as resp_admins:
                            if resp_admins.status == 200:
                                admins_data = await resp_admins.json()
                                admins = admins_data.get('members', [])
                                
                                bot_found = False
                                for admin in admins:
                                    if admin.get('is_bot', False):
                                        bot_found = True
                                        results.append(f"   • Бот в админах: ✅ ДА")
                                        # Проверка прав (если есть)
                                        permissions = admin.get('permissions', {})
                                        can_write = permissions.get('write', False)
                                        results.append(f"   • Право 'Писать посты': {'✅ Есть' if can_write else '❌ НЕТ'}")
                                        break
                                
                                if not bot_found:
                                    results.append(f"   • Бот в админах: ❌ НЕТ")
                            else:
                                results.append(f"   • Не удалось проверить права")
    except Exception as e:
        results.append(f"\n❌ **Права**: {str(e)}")
    
    # 4. Тестовая отправка
    try:
        test_text = f"🔍 Диагностическое сообщение {datetime.now().strftime('%H:%M:%S')}"
        url = "https://platform-api.max.ru/messages"
        headers = {
            "Authorization": MAX_TOKEN,
            "Content-Type": "application/json"
        }
        data = {
            "recipient": {"chat_id": str(MAX_CHANNEL_ID)},
            "message": {"text": test_text}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    results.append(f"\n✅ **Тестовая отправка**: успешно")
                else:
                    error = await resp.text()
                    results.append(f"\n❌ **Тестовая отправка**: ошибка {resp.status}")
                    results.append(f"   • {error}")
    except Exception as e:
        results.append(f"\n❌ **Тестовая отправка**: {str(e)}")
    
    # Отправляем результат
    await message.answer("\n".join(results))

@dp.message(Command("max_token"))
async def cmd_max_token(message: types.Message):
    """Проверка валидности токена"""
    await message.answer("🔄 Проверяю токен MAX...")
    try:
        url = "https://platform-api.max.ru/me"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await message.answer(
                        f"✅ **Токен работает!**\n\n"
                        f"📌 **Имя бота:** {data.get('name', 'неизвестно')}\n"
                        f"🆔 **ID бота:** `{data.get('user_id', 'неизвестно')}`\n"
                        f"📝 **Описание:** {data.get('description', 'нет')}\n"
                        f"👤 **Username:** @{data.get('username', 'нет')}"
                    )
                else:
                    error = await resp.text()
                    await message.answer(f"❌ **Ошибка {resp.status}**: {error}")
    except Exception as e:
        await message.answer(f"❌ **Ошибка**: {str(e)}")

@dp.message(Command("max_channel"))
async def cmd_max_channel(message: types.Message):
    """Информация о канале"""
    await message.answer(f"🔄 Получаю информацию о канале {MAX_CHANNEL_ID}...")
    try:
        url = f"https://platform-api.max.ru/chats/{MAX_CHANNEL_ID}"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await message.answer(
                        f"📊 **Информация о канале:**\n\n"
                        f"📌 **Название:** {data.get('title', 'неизвестно')}\n"
                        f"🆔 **ID:** `{data.get('chat_id')}`\n"
                        f"📊 **Тип:** {data.get('type', 'неизвестно')}\n"
                        f"📊 **Статус:** {data.get('status', 'неизвестно')}\n"
                        f"👥 **Участников:** {data.get('participants_count', 0)}\n"
                        f"👤 **Владелец:** `{data.get('owner_id', 'неизвестно')}`\n"
                        f"🔗 **Ссылка:** {data.get('link', 'нет')}"
                    )
                else:
                    error = await resp.text()
                    await message.answer(f"❌ **Ошибка {resp.status}**: {error}")
    except Exception as e:
        await message.answer(f"❌ **Ошибка**: {str(e)}")

@dp.message(Command("max_admins"))
async def cmd_max_admins(message: types.Message):
    """Список администраторов канала"""
    await message.answer(f"🔄 Получаю список администраторов канала {MAX_CHANNEL_ID}...")
    try:
        url = f"https://platform-api.max.ru/chats/{MAX_CHANNEL_ID}/members/admins"
        headers = {"Authorization": MAX_TOKEN}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    admins = data.get('members', [])
                    
                    result = f"👥 **Администраторы канала** (всего: {len(admins)}):\n\n"
                    
                    bot_in_admins = False
                    for i, admin in enumerate(admins, 1):
                        is_bot = admin.get('is_bot', False)
                        name = admin.get('name', 'неизвестно')
                        admin_id = admin.get('user_id', 'неизвестно')
                        
                        result += f"{i}. {'🤖' if is_bot else '👤'} {name}\n"
                        result += f"   🆔 ID: `{admin_id}`\n"
                        
                        if is_bot:
                            bot_in_admins = True
                            # Проверяем права
                            permissions = admin.get('permissions', {})
                            can_write = permissions.get('write', False)
                            result += f"   ✍️ Право писать: {'✅' if can_write else '❌'}\n"
                    
                    if not bot_in_admins:
                        result += f"\n❌ **Бот НЕ найден в администраторах!**"
                    
                    await message.answer(result)
                else:
                    error = await resp.text()
                    await message.answer(f"❌ **Ошибка {resp.status}**: {error}")
    except Exception as e:
        await message.answer(f"❌ **Ошибка**: {str(e)}")

@dp.message(Command("max_test"))
async def cmd_max_test(message: types.Message):
    """Тестовая отправка в канал"""
    await message.answer("🔄 Отправляю тестовое сообщение в канал MAX...")
    
    test_text = f"🧪 Тестовое сообщение от бота {datetime.now().strftime('%H:%M:%S')}"
    success = await send_to_max_channel(test_text)
    
    if success:
        await message.answer("✅ **Тест пройден!** Сообщение отправлено в канал.")
    else:
        await message.answer("❌ **Тест не пройден.** Проверьте логи для деталей.")

@dp.message()
async def forward_to_max(message: types.Message):
    """Пересылает сообщения из Telegram в MAX"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        logger.debug(f"Сообщение из другого чата: {message.chat.id}")
        return
    
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info("="*70)
    
    logger.info(f"👤 Отправитель: {message.from_user.full_name}")
    logger.info(f"🆔 ID отправителя: {message.from_user.id}")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    logger.info(f"💬 Чат ID: {message.chat.id}")
    
    text = message.text or message.caption or ""
    if text:
        logger.info(f"📝 Текст: {text}")
    
    if message.forward_date:
        logger.info("🔄 ЭТО ПЕРЕСЛАННОЕ СООБЩЕНИЕ")
        if message.forward_from_chat:
            logger.info(f"   📢 Из канала: {message.forward_from_chat.title}")
            text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
        elif message.forward_from:
            logger.info(f"   👤 От пользователя: {message.forward_from.full_name}")
            text = f"👤 Переслано от {message.forward_from.full_name}:\n\n{text}"
    
    attachments = await process_media(message)
    buttons = await extract_buttons(message)
    
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
        "📋 **Доступные команды:**\n"
        "• `/max_diag` - полная диагностика MAX\n"
        "• `/max_token` - проверка токена\n"
        "• `/max_channel` - информация о канале\n"
        "• `/max_admins` - администраторы канала\n"
        "• `/max_test` - тестовая отправка\n\n"
        "🔍 **Поддерживается:**\n"
        "• Текст\n"
        "• Фото\n"
        "• Пересланные сообщения\n"
        "• Кнопки-ссылки"
    )

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
