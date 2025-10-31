import logging
import os
import re
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, 
                         ConversationHandler, CallbackContext)
from telegram.ext import filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

ADMIN_CHAT_ID = "1079922982"

# Состояния диалога
(CITY, CAR_BRAND, CAR_MODEL, CAR_YEAR, VIN_OR_STS, VIN_TEXT, ENGINE_VOLUME, ENGINE_FUEL,
 PART_MAIN, PART_REFINEMENT, PART_SPECIFICS, PART_PHOTO, MORE_PARTS, 
 CONTACT_INFO, CONFIRMATION, EDIT_CHOICE) = range(16)

# Хранилище для напоминаний
user_reminders = {}

async def start(update: Update, context: CallbackContext):
    """Начало диалога, сбрасывает все состояния"""
    # Останавливаем все напоминания для этого пользователя
    user_id = update.effective_user.id
    if user_id in user_reminders:
        for task in user_reminders[user_id]:
            task.cancel()
        del user_reminders[user_id]
    
    # Полностью очищаем данные пользователя
    context.user_data.clear()
    
    welcome_text = """
🔧 *Добро пожаловать в АвтоЗапчасти 24/7!*

Я помогу вам найти нужные автозапчасти. 
Просто отвечайте на вопросы, и я соберу всю информацию для заказа.

*Давайте начнем! Из какого вы города?*
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    
    # Запускаем напоминания
    await schedule_reminders(update, context)
    
    return CITY

async def schedule_reminders(update: Update, context: CallbackContext):
    """Запланировать напоминания для пользователя"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id not in user_reminders:
        user_reminders[user_id] = []
    
    # Напоминание через 30 минут
    task_30min = asyncio.create_task(
        send_reminder(context, user_id, chat_id, 30*60, "⏰ Напоминаем о незавершенной заявке на автозапчасти! Продолжите оформление, чтобы мы могли помочь вам найти нужные детали.")
    )
    
    # Напоминание через 6 часов
    task_6hours = asyncio.create_task(
        send_reminder(context, user_id, chat_id, 6*60*60, "🕒 Вы начали оформлять заявку на запчасти 6 часов назад. Завершите оформление, чтобы получить детали быстрее!")
    )
    
    # Напоминание через 12 часов
    task_12hours = asyncio.create_task(
        send_reminder(context, user_id, chat_id, 12*60*60, "📅 Прошло 12 часов с момента начала оформления заявки. Это последнее напоминание - завершите заявку для получения помощи!")
    )
    
    user_reminders[user_id].extend([task_30min, task_6hours, task_12hours])

async def send_reminder(context: CallbackContext, user_id: int, chat_id: int, delay: int, message: str):
    """Отправить напоминание пользователю"""
    try:
        await asyncio.sleep(delay)
        # Проверяем, не завершил ли пользователь заявку
        if user_id in user_reminders:
            await context.bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")

async def get_city(update: Update, context: CallbackContext):
    """Получение города"""
    context.user_data['city'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"📍 *Город: {update.message.text}*\n\nУкажите *марку* автомобиля:", parse_mode='Markdown')
        return CAR_BRAND

async def get_car_brand(update: Update, context: CallbackContext):
    """Получение марки автомобиля"""
    context.user_data['car_brand'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"🚗 *Марка: {update.message.text}*\n\nУкажите *модель*:", parse_mode='Markdown')
        return CAR_MODEL

async def get_car_model(update: Update, context: CallbackContext):
    """Получение модели автомобиля"""
    context.user_data['car_model'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"🚙 *Модель: {update.message.text}*\n\nУкажите *год выпуска*:", parse_mode='Markdown')
        return CAR_YEAR

async def get_car_year(update: Update, context: CallbackContext):
    """Получение года выпуска"""
    year = update.message.text
    if not year.isdigit() or int(year) < 1950 or int(year) > 2030:
        await update.message.reply_text("❌ Укажите корректный год (например: 2018):")
        return CAR_YEAR
        
    context.user_data['car_year'] = year
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        keyboard = [
            ['📝 Ввести вин/стс вручную', '📷 Прикрепить фото вин/стс'],
            ['🚀 Пропустить']
        ]
        
        text = "🔢 *Укажите вин номер авто или номер стс*\n\nЭто поможет точнее подобрать запчасти. Можно:"
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return VIN_OR_STS

async def handle_vin_choice(update: Update, context: CallbackContext):
    """Обработка выбора варианта ввода VIN/СТС"""
    choice = update.message.text
    
    if choice == '📝 Ввести вин/стс вручную':
        await update.message.reply_text(
            "🔢 *Введите вин номер или номер стс:*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return VIN_TEXT
    elif choice == '📷 Прикрепить фото вин/стс':
        await update.message.reply_text(
            "📷 *Прикрепите фото вин номера или стс:*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return VIN_OR_STS
    else:  # Пропустить
        context.user_data['vin_skipped'] = True
        keyboard = [['1.0', '1.5', '1.6', '1.8'], ['2.0', '2.2', '2.5', '3.0'], ['📝 Другой объем']]
        await update.message.reply_text(
            "⚙️ *Какой объем двигателя?* (в литрах)",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return ENGINE_VOLUME

async def get_vin_text(update: Update, context: CallbackContext):
    """Получение VIN текстом"""
    context.user_data['vin_text'] = update.message.text
    context.user_data['vin_skipped'] = False
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        keyboard = [['1.0', '1.5', '1.6', '1.8'], ['2.0', '2.2', '2.5', '3.0'], ['📝 Другой объем']]
        await update.message.reply_text(
            "⚙️ *Какой объем двигателя?* (в литрах)",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return ENGINE_VOLUME

async def handle_vin_photo(update: Update, context: CallbackContext):
    """Обработка фото VIN/СТС"""
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        context.user_data['vin_photo'] = photo_file.file_id
        context.user_data['vin_skipped'] = False
        if context.user_data.get('editing'):
            del context.user_data['editing']
            return await show_summary(update, context)
        else:
            keyboard = [['1.0', '1.5', '1.6', '1.8'], ['2.0', '2.2', '2.5', '3.0'], ['📝 Другой объем']]
            await update.message.reply_text(
                "⚙️ *Какой объем двигателя?* (в литрах)",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            )
            return ENGINE_VOLUME
    else:
        await update.message.reply_text("📷 Пожалуйста, прикрепите фото вин/стс или выберите другую опцию")
        return VIN_OR_STS

async def get_engine_volume(update: Update, context: CallbackContext):
    """Получение объема двигателя"""
    if update.message.text == '📝 Другой объем':
        await update.message.reply_text("⚙️ *Введите объем двигателя:* (например: 1.4 или 2.0)", 
                                      parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return ENGINE_VOLUME
    
    # Проверяем, что введен корректный объем
    volume_text = update.message.text.replace(',', '.').strip()
    try:
        volume = float(volume_text)
        if volume <= 0 or volume > 10:
            await update.message.reply_text("❌ Укажите корректный объем двигателя (например: 1.6 или 2.0):")
            return ENGINE_VOLUME
    except ValueError:
        await update.message.reply_text("❌ Укажите объем в цифрах (например: 1.6 или 2.0):")
        return ENGINE_VOLUME
    
    context.user_data['engine_volume'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        keyboard = [['⛽ Бензин', '⛽ Дизель'], ['⚡ Гибрид', '🔋 Электро']]
        await update.message.reply_text(
            "⛽ *Тип топлива?*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return ENGINE_FUEL

async def get_fuel_type(update: Update, context: CallbackContext):
    """Получение типа топлива"""
    context.user_data['fuel_type'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        return await ask_parts(update, context)

async def ask_parts(update: Update, context: CallbackContext):
    """Начало ввода запчастей"""
    context.user_data['parts'] = []
    
    text = """
🔧 *Укажите нужную запчасть:*

*Примеры:*
• Тормозные колодки
• Фильтр масляный
• Аккумулятор
• Лобовое стекло
• *Любая другая запчасть*

*Что вам нужно?*"""
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    return PART_MAIN

async def get_part_main(update: Update, context: CallbackContext):
    """Получение основной информации о запчасти"""
    context.user_data['current_part'] = {'name': update.message.text, 'details': ''}
    
    keyboard = [
        ['✅ Знаю артикул/модель', '🚗 Нужна консультация'],
        ['📋 Есть фото/каталожный номер', '➡️ Пропустить']
    ]
    
    text = f"🔧 *Запчасть: {update.message.text}*\n\n*Нужно уточнить детали или пропустить?*"
    await update.message.reply_text(
        text, 
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return PART_REFINEMENT

async def handle_part_refinement(update: Update, context: CallbackContext):
    """Обработка уточнений по запчасти"""
    choice = update.message.text
    
    if choice == '✅ Знаю артикул/модель':
        text = "🔢 *Введите артикул, модель или каталожный номер:*"
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return PART_SPECIFICS
    elif choice == '🚗 Нужна консультация':
        context.user_data['current_part']['details'] = 'Нужна консультация менеджера'
        return await ask_part_photo(update, context)
    elif choice == '📋 Есть фото/каталожный номер':
        text = "📎 *Отправьте фото с каталожным номером или скриншот:*"
        await update.message.reply_text(text, parse_mode='Markdown')
        return PART_PHOTO
    else:  # Пропустить
        context.user_data['current_part']['details'] = 'Без уточнений'
        context.user_data['parts'].append(context.user_data['current_part'])
        return await ask_more_parts(update, context)

async def get_part_specifics(update: Update, context: CallbackContext):
    """Получение спецификаций запчасти"""
    context.user_data['current_part']['details'] = update.message.text
    return await ask_part_photo(update, context)

async def ask_part_photo(update: Update, context: CallbackContext):
    """Запрос фото запчасти"""
    keyboard = [['📷 Приложить фото'], ['🚀 Без фото']]
    
    part_info = f"*{context.user_data['current_part']['name']}*"
    if context.user_data['current_part']['details'] and context.user_data['current_part']['details'] != 'Без уточнений':
        part_info += f"\n*Детали:* {context.user_data['current_part']['details']}"
    
    text = f"🔧 *Запчасть добавлена:*\n{part_info}\n\n📷 *Приложить фото запчасти?*"
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return PART_PHOTO

async def handle_part_photo(update: Update, context: CallbackContext):
    """Обработка фото запчасти"""
    if update.message.text == '🚀 Без фото':
        context.user_data['parts'].append(context.user_data['current_part'])
        return await ask_more_parts(update, context)
    elif update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        context.user_data['current_part']['photo'] = photo_file.file_id
        context.user_data['parts'].append(context.user_data['current_part'])
        return await ask_more_parts(update, context)
    else:
        await update.message.reply_text("Отправьте фото или выберите опцию:")
        return PART_PHOTO

async def ask_more_parts(update: Update, context: CallbackContext):
    """Запрос на добавление еще запчастей"""
    keyboard = [['✅ Добавить еще'], ['❌ Это все']]
    count = len(context.user_data['parts'])
    await update.message.reply_text(
        f"📦 Добавлено {count} запчастей\n\nДобавить еще?", 
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return MORE_PARTS

async def handle_more_parts(update: Update, context: CallbackContext):
    """Обработка ответа о добавлении запчастей"""
    if update.message.text == '✅ Добавить еще':
        await update.message.reply_text("Укажите следующую запчасть:", reply_markup=ReplyKeyboardRemove())
        return PART_MAIN
    else:
        if context.user_data.get('editing'):
            del context.user_data['editing']
            return await show_summary(update, context)
        else:
            await update.message.reply_text(
                "📋 Укажите контакты:\n*Имя номер телефона*\nПример: *Иван +79165133244*", 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardRemove()
            )
            return CONTACT_INFO

async def get_contact_info(update: Update, context: CallbackContext):
    """Получение контактной информации"""
    try:
        parts = update.message.text.strip().split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Укажите имя и номер телефона через пробел. Пример: *Иван +79165133244*", parse_mode='Markdown')
            return CONTACT_INFO
        
        name = ' '.join(parts[:-1])
        phone = parts[-1]
        
        phone_clean = re.sub(r'[^\d+]', '', phone)
        
        if not re.match(r'^(\+7|8)\d{10}$', phone_clean):
            await update.message.reply_text("❌ Укажите номер в формате +79165133244 или 89165133244", parse_mode='Markdown')
            return CONTACT_INFO
        
        if phone_clean.startswith('8'):
            phone_clean = '+7' + phone_clean[1:]
        elif not phone_clean.startswith('+7'):
            phone_clean = '+7' + phone_clean
        
        context.user_data['contact_name'] = name
        context.user_data['contact_phone'] = phone_clean
        if context.user_data.get('editing'):
            del context.user_data['editing']
            return await show_summary(update, context)
        else:
            return await show_summary(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка обработки контактов: {e}")
        await update.message.reply_text("❌ Укажите имя и номер телефона через пробел. Пример: *Иван +79165133244*", parse_mode='Markdown')
        return CONTACT_INFO

async def show_summary(update: Update, context: CallbackContext):
    """Показать сводку заказа"""
    data = context.user_data
    text = f"📋 *СВОДКА ЗАКАЗА*\n\n📍 *Город:* {data['city']}\n🚗 *Авто:* {data['car_brand']} {data['car_model']} {data['car_year']}\n"
    
    # Всегда показываем двигатель, если есть данные
    if data.get('engine_volume') and data.get('fuel_type'):
        text += f"⚙️ *Двигатель:* {data['engine_volume']} {data['fuel_type']}\n"

    # Показываем VIN/СТС если они есть
    if not data.get('vin_skipped', True):
        if data.get('vin_text'):
            text += f"🔢 *VIN/СТС:* {data['vin_text']}\n"
        elif data.get('vin_photo'):
            text += f"🔢 *VIN/СТС:* 📷 (есть фото)\n"
    
    text += f"👤 *Контакт:* {data['contact_name']}, {data['contact_phone']}\n\n🔧 *ЗАПЧАСТИ:*"
    
    for i, part in enumerate(data['parts'], 1):
        text += f"\n{i}. *{part['name']}*"
        if part['details'] and part['details'] != 'Без уточнений':
            text += f"\n   Детали: {part['details']}"
        if part.get('photo'):
            text += " 📷"
    
    keyboard = [['🚀 Отправить заявку'], ['✏️ Исправить']]
    await update.message.reply_text(
        text, 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return CONFIRMATION

async def handle_confirmation(update: Update, context: CallbackContext):
    """Обработка подтверждения заказа"""
    logger.info(f"🔍 Обработка подтверждения: {update.message.text}")
    logger.info(f"🔍 Данные пользователя: {context.user_data}")
    
    if update.message.text == '🚀 Отправить заявку':
        # Останавливаем напоминания
        user_id = update.effective_user.id
        if user_id in user_reminders:
            for task in user_reminders[user_id]:
                task.cancel()
            del user_reminders[user_id]
        
        # Создаем ID заявки
        order_id = int(datetime.now().timestamp())
        logger.info(f"🔍 Создан order_id: {order_id}")
        
        try:
            # Отправляем уведомление администратору
            admin_text = f"🚨 НОВАЯ ЗАЯВКА #{order_id}\n"
            admin_text += f"📍 Город: {context.user_data['city']}\n"
            admin_text += f"🚗 Авто: {context.user_data['car_brand']} {context.user_data['car_model']} {context.user_data['car_year']}\n"
            
            # Двигатель
            if context.user_data.get('engine_volume') and context.user_data.get('fuel_type'):
                admin_text += f"⚙️ Двигатель: {context.user_data['engine_volume']} {context.user_data['fuel_type']}\n"
            
            # VIN/СТС
            if not context.user_data.get('vin_skipped', True):
                if context.user_data.get('vin_text'):
                    admin_text += f"🔢 VIN/СТС: {context.user_data['vin_text']}\n"
                elif context.user_data.get('vin_photo'):
                    admin_text += f"🔢 VIN/СТС: 📷 (фото ниже)\n"
            
            admin_text += f"👤 Клиент: {context.user_data['contact_name']}\n"
            admin_text += f"📞 Тел: {context.user_data['contact_phone']}\n\n"
            admin_text += "🔧 ЗАПРОШЕННЫЕ ЗАПЧАСТИ:\n"
            
            for i, part in enumerate(context.user_data['parts'], 1):
                admin_text += f"\n{i}. {part['name']}"
                if part['details'] and part['details'] != 'Без уточнений':
                    admin_text += f"\n   Детали: {part['details']}"
                if part.get('photo'):
                    admin_text += " 📷"
            
            logger.info(f"🔍 Отправляем администратору: {admin_text}")
            
            # Отправляем текст администратору
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
            logger.info("✅ Сообщение администратору отправлено")
            
            # Пересылаем фото вин/стс если есть
            if context.user_data.get('vin_photo'):
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=context.user_data['vin_photo'],
                    caption=f"🆔 Фото VIN/СТС для заявки #{order_id}"
                )
                logger.info("✅ Фото VIN отправлено")
            
            # Пересылаем фото запчастей если есть
            for i, part in enumerate(context.user_data['parts'], 1):
                if part.get('photo'):
                    await context.bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=part['photo'],
                        caption=f"🔧 Фото запчасти для заявки #{order_id}\n{part['name']}"
                    )
                    logger.info(f"✅ Фото запчасти {i} отправлено")
            
            await update.message.reply_text(
                f"🎉 *ЗАЯВКА #{order_id} ПРИНЯТА!*\n\n✅ Менеджер свяжется с вами в ближайшее время!", 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardRemove()
            )
            logger.info("✅ Пользователю отправлено подтверждение")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка отправки заявки: {e}", exc_info=True)
            await update.message.reply_text("❌ Ошибка отправки заявки. Попробуйте позже.")
        
        return ConversationHandler.END
    else:  # Исправить
        keyboard = [
            ['📍 Город', '🚗 Марка', '🚙 Модель'],
            ['📅 Год', '🔢 вин/Двигатель'],
            ['🔧 Запчасти', '👤 Контакты'],
            ['↩️ Назад к сводке']
        ]
        await update.message.reply_text(
            "✏️ *Что хотите исправить?*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return EDIT_CHOICE

async def handle_edit_choice(update: Update, context: CallbackContext):
    """Обработка выбора редактирования"""
    choice = update.message.text
    
    if choice == '↩️ Назад к сводке':
        return await show_summary(update, context)
    elif choice == '📍 Город':
        context.user_data['editing'] = True
        await update.message.reply_text("📍 *Введите новый город:*", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return CITY
    elif choice == '🚗 Марка':
        context.user_data['editing'] = True
        await update.message.reply_text("🚗 *Введите новую марку:*", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return CAR_BRAND
    elif choice == '🚙 Модель':
        context.user_data['editing'] = True
        await update.message.reply_text("🚙 *Введите новую модель:*", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return CAR_MODEL
    elif choice == '📅 Год':
        context.user_data['editing'] = True
        await update.message.reply_text("📅 *Введите новый год:*", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return CAR_YEAR
    elif choice == '🔢 вин/Двигатель':
        context.user_data['editing'] = True
        context.user_data.pop('vin_text', None)
        context.user_data.pop('vin_photo', None)
        context.user_data.pop('engine_volume', None)
        context.user_data.pop('fuel_type', None)
        context.user_data.pop('vin_skipped', None)
        
        keyboard = [
            ['📝 Ввести вин/стс вручную', '📷 Прикрепить фото вин/стс'],
            ['🚀 Пропустить']
        ]
        await update.message.reply_text(
            "🔢 *Укажите вин номер авто или номер стс:*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return VIN_OR_STS
    elif choice == '🔧 Запчасти':
        context.user_data['editing'] = True
        context.user_data['parts'] = []
        await update.message.reply_text("🔧 *Введите запчасти заново:*", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return PART_MAIN
    elif choice == '👤 Контакты':
        context.user_data['editing'] = True
        await update.message.reply_text("📋 *Введите новые контакты:*\nИмя номер телефона\nПример: Иван +79165133244", 
                                      parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return CONTACT_INFO

async def cancel(update: Update, context: CallbackContext):
    """Отмена диалога"""
    # Останавливаем напоминания
    user_id = update.effective_user.id
    if user_id in user_reminders:
        for task in user_reminders[user_id]:
            task.cancel()
        del user_reminders[user_id]
    
    await update.message.reply_text("Диалог прерван. Напишите /start для начала нового заказа", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def fallback_handler(update: Update, context: CallbackContext):
    """Обработчик непредвиденных сообщений"""
    await update.message.reply_text(
        "🤔 Я вас не понял. Пожалуйста, используйте кнопки или введите корректные данные.\n\n"
        "Если хотите начать заново, напишите /start",
        reply_markup=ReplyKeyboardRemove()
    )
    # Возвращаем текущее состояние, чтобы остаться в том же месте
    return context.user_data.get('conversation_state', CITY)

async def error_handler(update: Update, context: CallbackContext):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, напишите /start чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("❌ Ошибка: BOT_TOKEN не установлен!")
        return
    
    logger.info(f"🔍 ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    
    try:
        # Создаем Application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Настраиваем обработчики
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                CITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_city),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                CAR_BRAND: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_brand),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                CAR_MODEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_model),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                CAR_YEAR: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_year),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                VIN_OR_STS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_vin_choice),
                    MessageHandler(filters.PHOTO, handle_vin_photo),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                VIN_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_vin_text),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                ENGINE_VOLUME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_engine_volume),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                ENGINE_FUEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_fuel_type),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                PART_MAIN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_part_main),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                PART_REFINEMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_part_refinement),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                PART_SPECIFICS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_part_specifics),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                PART_PHOTO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_part_photo),
                    MessageHandler(filters.PHOTO, handle_part_photo),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                MORE_PARTS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_more_parts),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                CONTACT_INFO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact_info),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                CONFIRMATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
                EDIT_CHOICE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_choice),
                    MessageHandler(filters.ALL, fallback_handler)
                ],
            },
            fallbacks=[
                CommandHandler('start', start),
                CommandHandler('cancel', cancel),
                MessageHandler(filters.ALL, fallback_handler)
            ],
            allow_reentry=True
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        
        # Добавляем глобальный обработчик команды /start
        application.add_handler(CommandHandler("start", start))
        
        # Запускаем бота
        logger.info("🤖 Бот 'АвтоЗапчасти 24/7' запущен...")
        application.run_polling()
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}", exc_info=True)

if __name__ == '__main__':
    main()
