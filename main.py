import os
import asyncio
import logging
import aiohttp
import json
import html
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.markdown import hbold, hitalic, hlink, hcode, hpre, hunderline, hstrikethrough
from datetime import datetime

# === НАСТРОЙКА МАКСИМАЛЬНОГО ЛОГИРОВАНИЯ ===
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

logger.info("="*80)
logger.info("📋 ТЕКУЩИЕ НАСТРОЙКИ:")
logger.info(f"🤖 TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"👥 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
logger.info(f"🔑 MAX_TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
logger.info(f"📢 MAX_CHANNEL_ID: '{MAX_CHANNEL_ID}'")
logger.info("="*80)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def extract_text_with_entities(message: types.Message) -> str:
    """
    Извлекает текст с полным форматированием (жирный, курсив, ссылки и т.д.)
    Конвертирует Telegram entities в HTML для MAX
    """
    if not message.text and not message.caption:
        return ""
    
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    
    if not entities:
        logger.debug("📝 Нет форматирования, обычный текст")
        return text
    
    # Сортируем entities по позиции (от конца к началу, чтобы не сбивать индексы)
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
    
    html_text = text
    logger.info(f"🔍 Найдено {len(entities)} entities для форматирования")
    
    for entity in sorted_entities:
        start = entity.offset
        end = start + entity.length
        entity_text = text[start:end]
        
        # Экранируем HTML специальные символы
        entity_text = html.escape(entity_text)
        
        # Применяем форматирование в зависимости от типа entity
        if entity.type == "bold":
            logger.debug(f"   • Жирный текст: '{entity_text}'")
            replacement = f"<b>{entity_text}</b>"
        elif entity.type == "italic":
            logger.debug(f"   • Курсив: '{entity_text}'")
            replacement = f"<i>{entity_text}</i>"
        elif entity.type == "underline":
            logger.debug(f"   • Подчеркнутый: '{entity_text}'")
            replacement = f"<u>{entity_text}</u>"
        elif entity.type == "strikethrough":
            logger.debug(f"   • Зачеркнутый: '{entity_text}'")
            replacement = f"<s>{entity_text}</s>"
        elif entity.type == "code":
            logger.debug(f"   • Моноширинный: '{entity_text}'")
            replacement = f"<code>{entity_text}</code>"
        elif entity.type == "pre":
            logger.debug(f"   • Блок кода: '{entity_text}'")
            replacement = f"<pre>{entity_text}</pre>"
        elif entity.type == "text_link":
            url = entity.url
            logger.debug(f"   • Ссылка: '{entity_text}' -> {url}")
            replacement = f'<a href="{url}">{entity_text}</a>'
        elif entity.type == "text_mention":
            user = entity.user
            logger.debug(f"   • Упоминание: {entity_text} (ID: {user.id})")
            replacement = f'<a href="tg://user?id={user.id}">{entity_text}</a>'
        elif entity.type == "spoiler":
            logger.debug(f"   • Спойлер: '{entity_text}'")
            # MAX может не поддерживать спойлеры, используем жирный как fallback
            replacement = f"<b>[spoiler]</b>{entity_text}<b>[/spoiler]</b>"
        else:
            logger.warning(f"⚠️ Неизвестный тип entity: {entity.type}")
            continue
        
        # Заменяем текст с учетом уже сделанных замен
        html_text = html_text[:start] + replacement + html_text[end:]
    
    logger.info(f"📝 Итоговый HTML: {html_text[:200]}...")
    return html_text

async def send_to_max_with_logging(text: str, test_name: str = ""):
    """Отправка текста с максимальным логированием"""
    
    url = f"https://platform-api.max.ru/messages?chat_id={MAX_CHANNEL_ID}"
    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Формируем данные для отправки
    message_data = {
        "text": text,
        "parse_mode": "HTML"  # Включаем HTML-разметку
    }
    
    logger.info("="*80)
    logger.info(f"🔬 ТЕСТ: {test_name}")
    logger.info(f"📍 URL: {url}")
    logger.info(f"🔑 TOKEN: {MAX_TOKEN[:10]}...{MAX_TOKEN[-5:]}")
    logger.info(f"📋 HEADERS: {{'Authorization': '{MAX_TOKEN[:10]}...'}}")
    logger.info(f"📦 CHAT_ID: {MAX_CHANNEL_ID}")
    logger.info(f"📝 TEXT (raw): {text}")
    logger.info(f"📏 TEXT length: {len(text)}")
    logger.info(f"📦 FULL JSON: {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    logger.info("="*80)
    
    try:
        async with aiohttp.ClientSession() as session:
            start_time = asyncio.get_event_loop().time()
            
            async with session.post(url, headers=headers, json=message_data) as resp:
                response_time = (asyncio.get_event_loop().time() - start_time) * 1000
                response_text = await resp.text()
                
                logger.info("="*80)
                logger.info(f"📥 ОТВЕТ MAX API")
                logger.info(f"📊 HTTP STATUS: {resp.status}")
                logger.info(f"⏱ ВРЕМЯ: {response_time:.0f}ms")
                logger.info(f"📋 HEADERS: {dict(resp.headers)}")
                logger.info(f"📦 BODY: {response_text}")
                logger.info("="*80)
                
                if resp.status == 200:
                    logger.info(f"✅ ТЕСТ ПРОЙДЕН: {test_name}")
                    return True, response_text
                else:
                    logger.error(f"❌ ТЕСТ НЕ ПРОЙДЕН: {test_name}")
                    return False, response_text
                    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        logger.exception("ДЕТАЛИ:")
        return False, str(e)

@dp.message()
async def forward_to_max(message: types.Message):
    """Обработчик сообщений с полным форматированием"""
    
    if message.chat.id != TELEGRAM_GROUP_ID:
        return
    
    logger.info("="*80)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ ID: {message.message_id}")
    logger.info(f"👤 От: {message.from_user.full_name}")
    logger.info(f"🤖 Это бот: {message.from_user.is_bot}")
    
    # Извлекаем текст с форматированием
    formatted_text = extract_text_with_entities(message)
    
    # Добавляем подпись для пересланных сообщений
    if message.forward_date and message.forward_from_chat:
        source = message.forward_from_chat.title
        formatted_text = f"📢 Переслано из {source}:\n\n{formatted_text}"
        logger.info(f"🔄 Добавлена подпись об источнике: {source}")
    
    # Отправляем в MAX
    test_name = f"Текст от {message.from_user.full_name}"
    success, response = await send_to_max_with_logging(formatted_text, test_name)
    
    if success:
        logger.info("✅ СООБЩЕНИЕ УСПЕШНО ПЕРЕСЛАНО")
    else:
        logger.error("❌ НЕ УДАЛОСЬ ПЕРЕСЛАТЬ")
    
    logger.info("="*80)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✅ **БОТ-ПЕРЕСЫЛЬЩИК (ЭТАП 1)**\n\n"
        "📋 **ТЕСТИРУЕМЫЕ ФОРМАТЫ:**\n"
        "• Жирный текст\n"
        "• Курсив\n"
        "• Подчеркнутый\n"
        "• Зачеркнутый\n"
        "• Моноширинный\n"
        "• Ссылки в тексте\n"
        "• Цитаты\n"
        "• Эмодзи\n"
        "• Комбинации\n\n"
        f"📤 **Источник:** группа `{TELEGRAM_GROUP_ID}`\n"
        f"📥 **Приёмник:** канал `{MAX_CHANNEL_ID}`\n\n"
        "🔍 **Логирование включено** — проверяйте логи после каждого теста"
    )

@dp.message(Command("test1"))
async def cmd_test1(message: types.Message):
    """Отправляет тестовый набор для проверки"""
    test_text = (
        "<b>Жирный текст</b>\n"
        "<i>Курсив</i>\n"
        "<u>Подчеркнутый</u>\n"
        "<s>Зачеркнутый</s>\n"
        "<code>Моноширинный</code>\n"
        '<a href="https://example.com">Ссылка</a>\n'
        "Эмодзи: 👋 🌍 🎉\n"
        "> Цитата\n"
        "<b><i>Жирный + Курсив</i></b>\n"
        "Обычный текст со <b>вставкой</b> форматирования"
    )
    
    await message.answer("🔄 Отправляю тестовый набор в группу...")
    await message.answer(test_text, parse_mode="HTML")

async def main():
    logger.info("="*80)
    logger.info("🚀 ЗАПУСК БОТА-ПЕРЕСЫЛЬЩИКА (ЭТАП 1)")
    logger.info(f"📤 TELEGRAM_GROUP_ID: {TELEGRAM_GROUP_ID}")
    logger.info(f"📥 MAX_CHANNEL_ID: {MAX_CHANNEL_ID}")
    logger.info("📋 РЕЖИМ: ПРОВЕРКА ФОРМАТИРОВАНИЯ")
    logger.info("="*80)
    
    await telegram_bot.delete_webhook()
    await dp.start_polling(telegram_bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
