import os
import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# === НАСТРОЙКА МАКСИМАЛЬНО ПОДРОБНОГО ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG уровень для максимальной детализации
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
logger.info(f"📢 MAX_CHANNEL_ID: {MAX_CHANNEL_ID} (тип: {type(MAX_CHANNEL_ID)})")
logger.info("="*70)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === КЛАСС ДЛЯ РАБОТЫ С MAX API С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ ===
class MaxBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://platform-api.max.ru"
        self.session = None
        logger.info("✅ MaxBot инициализирован")
        logger.info(f"   Base URL: {self.base_url}")
        logger.info(f"   Token: {token[:10]}...{token[-5:]}")
        
    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            logger.debug("🔌 Сессия создана")
    
    async def _request(self, endpoint: str, data: dict = None, method: str = "POST"):
        """Универсальный метод для запросов к MAX API с детальным логированием"""
        await self._ensure_session()
        
        # Формируем URL
        url = f"{self.base_url}/{endpoint}"
        
        # Формируем заголовки
        headers = {
            "Authorization": f"{self.token}",
            "Content-Type": "application/json",
            "User-Agent": "Telegram-Forward-Bot/1.0"
        }
        
        # Логируем ВСЕ детали запроса
        logger.info("="*70)
        logger.info(f"📤 MAX API ЗАПРОС [{method}]")
        logger.info(f"   📍 Endpoint: {endpoint}")
        logger.info(f"   🔗 Полный URL: {url}")
        logger.info(f"   📋 Headers: { {k:v[:20]+'...' if k=='Authorization' else v for k,v in headers.items()} }")
        
        if data:
            logger.info(f"   📦 Данные запроса:")
            logger.info(f"      chat_id: {data.get('chat_id')} (тип: {type(data.get('chat_id'))})")
            logger.info(f"      text: {data.get('text', '')[:50]}...")
            logger.info(f"      parse_mode: {data.get('parse_mode')}")
            logger.info(f"   📝 Полный JSON: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            if method == "GET":
                async with self.session.get(url, headers=headers) as resp:
                    response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                    response_text = await resp.text()
                    
                    # Логируем ответ
                    logger.info(f"📥 MAX API ОТВЕТ [статус: {resp.status}]")
                    logger.info(f"   ⏱ Время ответа: {response_time:.0f}ms")
                    logger.info(f"   📋 Headers ответа: {dict(resp.headers)}")
                    
                    try:
                        response_json = json.loads(response_text)
                        logger.info(f"   📦 Тело ответа (JSON):")
                        logger.info(f"      {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                        return response_json
                    except:
                        logger.info(f"   📄 Тело ответа (текст): {response_text[:500]}")
                        return {"raw_response": response_text}
            else:
                async with self.session.post(url, headers=headers, json=data) as resp:
                    response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                    response_text = await resp.text()
                    
                    # Логируем ответ
                    logger.info(f"📥 MAX API ОТВЕТ [статус: {resp.status}]")
                    logger.info(f"   ⏱ Время ответа: {response_time:.0f}ms")
                    logger.info(f"   📋 Headers ответа: {dict(resp.headers)}")
                    
                    # Парсим JSON ответ
                    try:
                        response_json = json.loads(response_text)
                        logger.info(f"   📦 Тело ответа (JSON):")
                        logger.info(f"      {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                        
                        # Анализируем ошибки
                        if resp.status != 200:
                            if response_json.get('code') == 'proto.payload':
                                logger.error("❌ ОШИБКА: Неизвестный получатель (Unknown recipient)")
                                logger.error("   Возможные причины:")
                                logger.error("   • Неправильный chat_id")
                                logger.error("   • Бот не добавлен в канал")
                                logger.error("   • У бота нет прав на отправку")
                                logger.error("   • Канал не активен")
                            elif response_json.get('code') == 'verify.token':
                                logger.error("❌ ОШИБКА: Неверный токен MAX")
                        
                        return response_json
                    except:
                        logger.info(f"   📄 Тело ответа (текст): {response_text[:500]}")
                        return {"raw_response": response_text}
                        
        except aiohttp.ClientConnectorError as e:
            logger.error(f"❌ Ошибка подключения к MAX API: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            logger.exception("Детальный стек ошибки:")
            raise
    
    async def get_chats(self):
        """Получение списка доступных чатов"""
        logger.info("🔍 Запрос списка всех доступных чатов")
        return await self._request("chats", method="GET")
    
    async def get_chat_info(self, chat_id):
        """Получение информации о конкретном чате"""
        logger.info(f"🔍 Запрос информации о чате: {chat_id}")
        return await self._request(f"chats/{chat_id}", method="GET")
    
    async def send_message(self, chat_id, text: str, reply_markup=None):
        """Отправка текстового сообщения с поддержкой разных форматов chat_id"""
        logger.info("="*70)
        logger.info("📤 ПОДГОТОВКА К ОТПРАВКЕ СООБЩЕНИЯ В MAX")
        
        # Пробуем разные форматы chat_id
        chat_id_original = chat_id
        chat_id_variants = []
        
        # Определяем тип входных данных
        if isinstance(chat_id, str):
            if chat_id.startswith('-'):
                # Вариант 1: как есть (строка с минусом)
                chat_id_variants.append(chat_id)
                # Вариант 2: как число
                try:
                    chat_id_variants.append(int(chat_id))
                except:
                    pass
            else:
                # Вариант 3: как есть (строка)
                chat_id_variants.append(chat_id)
                # Вариант 4: как число если можно
                try:
                    if chat_id.isdigit():
                        chat_id_variants.append(int(chat_id))
                except:
                    pass
        elif isinstance(chat_id, int):
            # Вариант 5: как число
            chat_id_variants.append(chat_id)
            # Вариант 6: как строка
            chat_id_variants.append(str(chat_id))
        
        logger.info(f"📋 Тестируемые форматы chat_id:")
        for i, variant in enumerate(chat_id_variants, 1):
            logger.info(f"   Вариант {i}: {variant} (тип: {type(variant)})")
        
        # Пробуем каждый вариант
        for i, variant in enumerate(chat_id_variants, 1):
            logger.info(f"🔄 Попытка {i} с chat_id = {variant} (тип: {type(variant)})")
            
            data = {
                "chat_id": variant,
                "text": text,
                "parse_mode": "HTML"
            }
            
            if reply_markup:
                data["reply_markup"] = reply_markup
                logger.info(f"🔘 Добавлены кнопки: {reply_markup}")
            
            result = await self._request("messages", data)
            
            # Если успешно (статус 200) - возвращаем результат
            if isinstance(result, dict) and result.get('ok') == True:
                logger.info(f"✅ УСПЕХ! Вариант {i} сработал")
                return result
            
            # Если ошибка "Unknown recipient" - пробуем следующий вариант
            if isinstance(result, dict) and result.get('code') == 'proto.payload':
                logger.warning(f"⚠️ Вариант {i} не сработал (Unknown recipient)")
                continue
            
            # Если другая ошибка - логируем и продолжаем
            logger.warning(f"⚠️ Вариант {i} вернул ошибку: {result}")
        
        logger.error("❌ Ни один из вариантов chat_id не сработал")
        return {"error": "All chat_id variants failed"}

# Инициализируем MAX бота
max_bot = MaxBot(token=MAX_TOKEN)

async def download_file(file_id: str) -> str:
    """Скачивает файл из Telegram и возвращает ссылку на него"""
    try:
        logger.info(f"📥 Скачивание файла из Telegram: {file_id}")
        file = await telegram_bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        logger.info(f"✅ Файл скачан: {file_url}")
        logger.info(f"   Путь: {file.file_path}")
        logger.info(f"   Размер: {file.file_size if hasattr(file, 'file_size') else 'неизвестно'} байт")
        return file_url
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания файла: {e}")
        raise

def extract_buttons(message: types.Message):
    """Извлекает кнопки-ссылки из сообщения"""
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        logger.info(f"🔘 Найдены кнопки: {len(message.reply_markup.inline_keyboard)} рядов")
        for row in message.reply_markup.inline_keyboard:
            button_row = []
            for button in row:
                if button.url:
                    button_row.append({
                        "text": button.text,
                        "url": button.url
                    })
                    logger.info(f"   Кнопка: '{button.text}' -> {button.url}")
            if button_row:
                buttons.append(button_row)
    return buttons

# === КОМАНДА ДЛЯ ДЕТАЛЬНОГО ТЕСТИРОВАНИЯ ===
@dp.message(Command("test_max"))
async def cmd_test_max(message: types.Message):
    """Детальное тестирование всех аспектов подключения к MAX"""
    await message.answer("🔄 Запускаю детальную диагностику MAX...")
    
    try:
        # 1. Проверяем базовое подключение
        await message.answer("1️⃣ Проверка подключения к MAX API...")
        test_data = {"test": "connection"}
        test_result = await max_bot._request("test", test_data)
        await message.answer(f"   Результат: {test_result}")
        
        # 2. Получаем список всех чатов
        await message.answer("2️⃣ Получение списка доступных чатов...")
        chats = await max_bot.get_chats()
        
        # Форматируем вывод
        if isinstance(chats, dict) and chats.get('chats'):
            result = "✅ **Доступные чаты:**\n\n"
            for chat in chats['chats']:
                result += f"📌 **Название:** {chat.get('title', 'Без названия')}\n"
                result += f"🆔 **ID:** `{chat.get('chat_id')}`\n"
                result += f"📊 **Тип:** {chat.get('type')}\n"
                result += f"📊 **Статус:** {chat.get('status')}\n"
                result += f"👥 **Участников:** {chat.get('participants_count')}\n"
                result += f"👤 **Владелец:** {chat.get('owner_id')}\n"
                result += f"🔗 **Ссылка:** {chat.get('link', 'нет')}\n"
                result += "-" * 30 + "\n"
            await message.answer(result)
        else:
            await message.answer(f"❌ Не удалось получить список чатов: {chats}")
        
        # 3. Проверяем конкретный канал
        await message.answer(f"3️⃣ Проверка канала с ID {MAX_CHANNEL_ID}...")
        try:
            chat_info = await max_bot.get_chat_info(MAX_CHANNEL_ID)
            await message.answer(f"   Информация о канале: {chat_info}")
        except Exception as e:
            await message.answer(f"   ❌ Ошибка: {e}")
        
        # 4. Пробуем отправить тестовое сообщение
        await message.answer("4️⃣ Попытка отправить тестовое сообщение...")
        send_result = await max_bot.send_message(
            MAX_CHANNEL_ID, 
            "🔄 Тестовое сообщение из диагностики"
        )
        await message.answer(f"   Результат отправки: {send_result}")
        
    except Exception as e:
        await message.answer(f"❌ Критическая ошибка: {e}")
        logger.exception("Ошибка в диагностике:")

# === КОМАНДА ДЛЯ ПРОВЕРКИ РАЗНЫХ ФОРМАТОВ ID ===
@dp.message(Command("test_ids"))
async def cmd_test_ids(message: types.Message):
    """Тестирует разные форматы ID канала"""
    await message.answer("🔄 Тестирую разные форматы ID...")
    
    variants = [
        MAX_CHANNEL_ID,  # как есть
        str(MAX_CHANNEL_ID),  # как строка
        int(MAX_CHANNEL_ID) if str(MAX_CHANNEL_ID).lstrip('-').isdigit() else MAX_CHANNEL_ID,  # как число
        MAX_CHANNEL_ID.replace('-', ''),  # без минуса
    ]
    
    results = []
    for i, variant in enumerate(set(str(v) for v in variants if v), 1):
        await message.answer(f"🔄 Тест {i}: ID = {variant}")
        try:
            result = await max_bot.send_message(variant, f"Тест {i} с ID {variant}")
            results.append(f"✅ Вариант {i}: успех - {result}")
        except Exception as e:
            results.append(f"❌ Вариант {i}: ошибка - {e}")
    
    await message.answer("\n".join(results))

# === ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ===
@dp.message()
async def forward_to_max(message: types.Message):
    # Проверка источника
    if message.chat.id != TELEGRAM_GROUP_ID:
        logger.debug(f"Сообщение из другого чата: {message.chat.id} (нужен: {TELEGRAM_GROUP_ID})")
        return
    
    # МАКСИМАЛЬНО ПОДРОБНОЕ ЛОГИРОВАНИЕ
    logger.info("="*70)
    logger.info("📨 ПОЛУЧЕНО НОВОЕ СООБЩЕНИЕ ИЗ TELEGRAM")
    logger.info("="*70)
    
    # Базовая информация
    logger.info(f"🆔 ID сообщения: {message.message_id}")
    logger.info(f"👤 Отправитель: {message.from_user.full_name} (ID: {message.from_user.id})")
    logger.info(f"📱 Username: @{message.from_user.username if message.from_user.username else 'нет'}")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    logger.info(f"💬 Чат: {message.chat.title} (ID: {message.chat.id})")
    logger.info(f"📌 Тип чата: {message.chat.type}")
    logger.info(f"🕐 Время: {message.date}")
    
    # Информация о пересылке
    if message.forward_date:
        logger.info("🔄 ЭТО ПЕРЕСЛАННОЕ СООБЩЕНИЕ:")
        logger.info(f"  📅 Оригинальная дата: {message.forward_date}")
        if message.forward_from_chat:
            logger.info(f"  📢 Из канала: {message.forward_from_chat.title}")
            logger.info(f"  🆔 ID канала: {message.forward_from_chat.id}")
        if message.forward_from:
            logger.info(f"  👤 От пользователя: {message.forward_from.full_name}")
    
    # Текст сообщения
    text = message.text or message.caption or ''
    if text:
        logger.info(f"📝 Текст: {text}")
        logger.info(f"📏 Длина: {len(text)} символов")
    
    # Тип контента
    if message.photo:
        logger.info(f"🖼 ТИП: ФОТО")
        logger.info(f"   Количество версий: {len(message.photo)}")
        for i, photo in enumerate(message.photo):
            logger.info(f"   Версия {i+1}: {photo.width}x{photo.height}, file_id: {photo.file_id}")
        main_photo = message.photo[-1]
        logger.info(f"   ✅ Используем версию: {main_photo.width}x{main_photo.height}")
        
    elif message.video:
        logger.info(f"🎥 ТИП: ВИДЕО")
        logger.info(f"   Размер: {message.video.width}x{message.video.height}")
        logger.info(f"   Длительность: {message.video.duration} сек")
        logger.info(f"   file_id: {message.video.file_id}")
        
    elif message.voice:
        logger.info(f"🎤 ТИП: ГОЛОСОВОЕ")
        logger.info(f"   Длительность: {message.voice.duration} сек")
        
    elif message.document:
        logger.info(f"📄 ТИП: ДОКУМЕНТ")
        logger.info(f"   Имя: {message.document.file_name}")
        logger.info(f"   MIME: {message.document.mime_type}")
        
    elif message.text:
        logger.info(f"📝 ТИП: ТЕКСТ")
    
    # Альбом
    if message.media_group_id:
        logger.info(f"🖼👥 ЭТО АЛЬБОМ")
        logger.info(f"   ID группы: {message.media_group_id}")
    
    # Кнопки
    buttons = extract_buttons(message)
    
    logger.info("="*70)
    
    # ПЕРЕСЫЛКА
    try:
        # Формируем текст с информацией об источнике
        final_text = text
        if message.forward_from_chat and text:
            final_text = f"📢 Переслано из {message.forward_from_chat.title}:\n\n{text}"
            logger.info(f"📝 Добавлена подпись об источнике")
        
        logger.info(f"🚀 НАЧАЛО ПЕРЕСЫЛКИ В MAX")
        logger.info(f"📤 Целевой канал ID: {MAX_CHANNEL_ID}")
        logger.info(f"📤 Текст для отправки: {final_text[:100]}...")
        
        reply_markup = {"inline_keyboard": buttons} if buttons else None
        
        # Определяем тип и отправляем
        if message.photo:
            logger.info("🖼 Обработка фото...")
            photo = message.photo[-1]
            photo_url = await download_file(photo.file_id)
            logger.info(f"📤 Отправка фото в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
            
        elif message.video:
            logger.info("🎥 Обработка видео...")
            video_url = await download_file(message.video.file_id)
            logger.info(f"📤 Отправка видео в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
            
        elif message.voice:
            logger.info("🎤 Обработка голосового...")
            voice_url = await download_file(message.voice.file_id)
            logger.info(f"📤 Отправка голосового в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
            
        elif message.document:
            logger.info("📄 Обработка документа...")
            doc_url = await download_file(message.document.file_id)
            logger.info(f"📤 Отправка документа в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
            
        elif message.text:
            logger.info("📝 Обработка текста...")
            logger.info(f"📤 Отправка текста в MAX...")
            result = await max_bot.send_message(MAX_CHANNEL_ID, final_text, reply_markup)
        
        # Анализируем результат
        if isinstance(result, dict):
            if result.get('ok') == True:
                logger.info("✅ СООБЩЕНИЕ УСПЕШНО ОТПРАВЛЕНО В MAX!")
            elif result.get('code') == 'proto.payload':
                logger.error("❌ MAX НЕ НАШЕЛ ПОЛУЧАТЕЛЯ (Unknown recipient)")
                logger.error("   🔍 Возможные причины:")
                logger.error("   1️⃣ Неправильный ID канала — проверьте MAX_CHANNEL_ID")
                logger.error("   2️⃣ Бот не добавлен в канал — проверьте администраторов")
                logger.error("   3️⃣ У бота нет прав на отправку — включите 'Писать посты'")
                logger.error("   4️⃣ Канал не активен — проверьте статус")
                logger.error("   5️⃣ Не тот формат ID — попробуйте другой (с минусом/без)")
            else:
                logger.warning(f"⚠️ Неизвестный ответ от MAX: {result}")
        
        logger.info(f"📥 Полный ответ от MAX: {result}")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детальный стек ошибки:")

# === СТАНДАРТНЫЕ КОМАНДЫ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **Бот-пересыльщик MAX**\n\n"
        "📋 **Доступные команды:**\n"
        "• `/start` — это сообщение\n"
        "• `/get_my_chats` — список чатов в MAX\n"
        "• `/test_max` — полная диагностика MAX\n"
        "• `/test_ids` — тест разных форматов ID\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📊 **Статус:** ожидание сообщений..."
    )

@dp.message(Command("get_my_chats"))
async def cmd_get_my_chats(message: types.Message):
    """Получение списка чатов"""
    await message.answer("🔄 Запрашиваю список чатов...")
    try:
        chats = await max_bot.get_chats()
        
        if isinstance(chats, dict) and chats.get('chats'):
            result = "✅ **Доступные чаты:**\n\n"
            for chat in chats['chats']:
                result += f"📌 **Название:** {chat.get('title', 'Без названия')}\n"
                result += f"🆔 **ID:** `{chat.get('chat_id')}`\n"
                result += f"📊 **Тип:** {chat.get('type')}\n"
                result += f"📊 **Статус:** {chat.get('status')}\n"
                result += f"👥 **Участников:** {chat.get('participants_count')}\n"
                result += f"👤 **Владелец:** {chat.get('owner_id')}\n"
                result += f"🔗 **Ссылка:** {chat.get('link', 'нет')}\n"
                result += "-" * 30 + "\n"
            await message.answer(result)
        else:
            await message.answer(f"❌ Ответ API: {chats}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def main():
    logger.info("="*70)
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА")
    logger.info("="*70)
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info(f"🌐 MAX API URL: https://platform-api.max.ru")
    logger.info("="*70)
    
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    asyncio.run(main())
