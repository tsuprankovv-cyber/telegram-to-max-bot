import os
import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

async def send_test_to_max(text: str):
    """
    ПРОСТЕЙШАЯ функция отправки только текста в MAX
    С МАКСИМАЛЬНЫМ ЛОГИРОВАНИЕМ каждого шага
    """
    
    # 1. Формируем URL с chat_id как query-параметр (СОГЛАСНО ДОКУМЕНТАЦИИ)
    chat_id_str = str(MAX_CHANNEL_ID).strip()
    url = f"https://platform-api.max.ru/messages?chat_id={chat_id_str}"
    
    # 2. Формируем заголовки
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Telegram-Test-Bot/1.0"
    }
    
    # 3. Формируем ТОЛЬКО сообщение (без recipient)
    message_data = {"text": text}
    
    # 4. ЛОГИРУЕМ ВСЁ ДО МЕЛЬЧАЙШИХ ДЕТАЛЕЙ
    logger.info("="*70)
    logger.info("📤 ПОДГОТОВКА ЗАПРОСА К MAX API")
    logger.info(f"📍 ПОЛНЫЙ URL: {url}")
    logger.info(f"🔑 TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
    logger.info(f"📋 HEADERS: { {k: v[:20]+'...' if k == 'Authorization' else v for k, v in headers.items()} }")
    logger.info(f"📦 CHAT_ID (str): '{chat_id_str}'")
    logger.info(f"📦 CHAT_ID (type): {type(chat_id_str)}")
    logger.info(f"📝 TEXT: '{text}'")
    logger.info(f"📝 TEXT length: {len(text)}")
    logger.info(f"📦 FULL JSON BODY: {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    logger.info("="*70)
    
    # 5. Отправляем запрос
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("🔄 СОЗДАНИЕ СЕССИИ...")
            
            start_time = asyncio.get_event_loop().time()
            
            logger.info(f"🚀 ОТПРАВКА POST запроса на {url}")
            async with session.post(url, headers=headers, json=message_data) as resp:
                
                response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                
                # 6. ЧИТАЕМ ОТВЕТ
                response_text = await resp.text()
                
                logger.info("="*70)
                logger.info("📥 ПОЛУЧЕН ОТВЕТ ОТ MAX API")
                logger.info(f"📊 HTTP STATUS: {resp.status}")
                logger.info(f"⏱ ВРЕМЯ ОТВЕТА: {response_time:.0f}ms")
                logger.info(f"📋 RESPONSE HEADERS: {dict(resp.headers)}")
                logger.info(f"📦 RESPONSE BODY: {response_text}")
                
                # 7. АНАЛИЗИРУЕМ ОТВЕТ
                if resp.status == 200:
                    logger.info("✅ УСПЕХ! Сообщение отправлено")
                    try:
                        response_json = json.loads(response_text)
                        logger.info(f"📊 ПАРСИНГ JSON: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                    except:
                        pass
                    return True
                else:
                    logger.error("❌ ОШИБКА!")
                    
                    # ДЕТАЛЬНЫЙ АНАЛИЗ ОШИБКИ 400
                    if resp.status == 400:
                        logger.error("🔍 АНАЛИЗ ОШИБКИ 400:")
                        
                        if 'proto.payload' in response_text:
                            logger.error("   • КОД: proto.payload")
                            logger.error("   • СООБЩЕНИЕ: Unknown recipient")
                            logger.error("   • ПРИЧИНЫ:")
                            logger.error("     1️⃣ chat_id не существует или недоступен боту")
                            logger.error("     2️⃣ Неправильный формат chat_id")
                            logger.error("     3️⃣ Бот не имеет прав на отправку")
                            
                            # Проверяем chat_id
                            logger.error(f"   • ИСПОЛЬЗУЕМЫЙ chat_id: '{chat_id_str}'")
                            
                            # Пробуем альтернативный формат (без кавычек в логе)
                            try:
                                chat_id_int = int(chat_id_str)
                                logger.error(f"   • АЛЬТЕРНАТИВНЫЙ ФОРМАТ (int): {chat_id_int}")
                            except:
                                pass
                    
                    return False
                    
    except aiohttp.ClientConnectorError as e:
        logger.error(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ НЕИЗВЕСТНАЯ ОШИБКА: {e}")
        logger.exception("ДЕТАЛЬНЫЙ СТЕК:")
        return False

@dp.message()
async def forward_to_max(message: types.Message):
    """Максимально простой тест - только цифры"""
    
    # Проверяем, что сообщение из нужной группы
    if message.chat.id != TELEGRAM_GROUP_ID:
        logger.debug(f"Сообщение из другого чата: {message.chat.id}")
        return
    
    # Логируем полученное сообщение
    logger.info("="*70)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    logger.info(f"💬 Чат: {message.chat.id}")
    
    # Берем текст сообщения
    text = message.text or message.caption or ""
    logger.info(f"📝 Текст: '{text}'")
    
    # Отправляем только текст в MAX
    logger.info(f"🚀 Отправляем в MAX...")
    success = await send_test_to_max(text)
    
    if success:
        logger.info(f"✅ Успешно переслано: '{text}'")
    else:
        logger.error(f"❌ Не удалось переслать: '{text}'")
    
    logger.info("="*70)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **ТЕСТОВЫЙ БОТ-ПЕРЕСЫЛЬЩИК**\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "📋 **Режим:** ТОЛЬКО ТЕКСТ, максимальное логирование\n\n"
        "Отправьте любое сообщение с цифрой в группу"
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Ручная тестовая отправка"""
    test_text = f"🔍 ТЕСТ {datetime.now().strftime('%H:%M:%S')}"
    await message.answer(f"🔄 Отправляю тест: '{test_text}'")
    success = await send_test_to_max(test_text)
    if success:
        await message.answer("✅ ТЕСТ ПРОЙДЕН!")
    else:
        await message.answer("❌ ТЕСТ НЕ ПРОЙДЕН. Проверьте логи.")

# Добавляем datetime для команды /test
from datetime import datetime

async def main():
    logger.info("="*70)
    logger.info("🚀 ЗАПУСК ТЕСТОВОГО БОТА-ПЕРЕСЫЛЬЩИКА")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
    logger.info("📋 РЕЖИМ: ТОЛЬКО ТЕКСТ, МАКСИМАЛЬНОЕ ЛОГИРОВАНИЕ")
    logger.info("="*70)
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
