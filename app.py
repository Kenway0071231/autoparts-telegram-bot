import logging
import os
import re
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, 
                         ConversationHandler, CallbackContext, ContextTypes)
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

class Database:
    def save_order(self, order_data):
        # Теперь просто логируем, без сохранения на сервере
        try:
            order_data['order_id'] = int(datetime.now().timestamp())
            order_data['created_at'] = datetime.now().isoformat()
            
            # Логируем заказ
            logger.info(f"📦 НОВЫЙ ЗАКАЗ #{order_data['order_id']}")
            logger.info(f"📍 Город: {order_data['city']}")
            logger.info(f"🚗 Авто: {order_data['car_brand']} {order_data['car_model']} {order_data['car_year']}")
            
            if not order_data.get('vin_skipped', True):
                if order_data.get('vin_text'):
                    logger.info(f"🔢 ВИН/СТС: {order_data['vin_text']}")
                elif order_data.get('vin_photo'):
                    logger.info(f"🔢 ВИН/СТС: 📷 (есть фото)")
            else:
                # ИСПРАВЛЕНО: было data, теперь order_data
                logger.info(f"⚙️ Двигатель: {order_data.get('engine_volume', '')} {order_data.get('fuel_type', '')}")
            
            logger.info(f"👤 Контакт: {order_data['contact_name']} {order_data['contact_phone']}")
            logger.info(f"🔧 Запчасти: {len(order_data['parts'])} шт.")
            
            for i, part in enumerate(order_data['parts'], 1):
                logger.info(f"  {i}. {part['name']} - {part.get('details', '')}")
            
            logger.info("=" * 50)
            return order_data['order_id']
            
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
            return None

db = Database()

async def start(update: Update, context: CallbackContext):
    # Останавливаем все напоминания для этого пользователя
    user_id = update.effective_user.id
    if user_id in user_reminders:
        for task in user_reminders[user_id]:
            task.cancel()
        del user_reminders[user_id]
    
    context.user_data.clear()
    
    welcome_text = """
🔧 *Добро пожаловать в АвтоЗапчасти 24/7!*

Я помогу вам найти нужные автозапчасти. 
Просто отвечайте на вопросы, и я соберу всю информацию для заказа.

*Давайте начнем! Из какого вы города?*
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
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
    context.user_data['city'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"📍 *Город: {update.message.text}*\n\nУкажите *марку* автомобиля:", parse_mode='Markdown')
        return CAR_BRAND

async def get_car_brand(update: Update, context: CallbackContext):
    context.user_data['car_brand'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"🚗 *Марка: {update.message.text}*\n\nУкажите *модель*:", parse_mode='Markdown')
        return CAR_MODEL

async def get_car_model(update: Update, context: CallbackContext):
    context.user_data['car_model'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        await update.message.reply_text(f"🚙 *Модель: {update.message.text}*\n\nУкажите *год выпуска*:", parse_mode='Markdown')
        return CAR_YEAR

async def get_car_year(update: Update, context: CallbackContext):
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
    context.user_data['vin_text'] = update.message.text
    context.user_data['vin_skipped'] = False
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        return await ask_parts(update, context)

async def handle_vin_photo(update: Update, context: CallbackContext):
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        context.user_data['vin_photo'] = photo_file.file_id
        context.user_data['vin_skipped'] = False
        if context.user_data.get('editing'):
            del context.user_data['editing']
            return await show_summary(update, context)
        else:
            return await ask_parts(update, context)
    else:
        await update.message.reply_text("📷 Пожалуйста, прикрепите фото вин/стс или выберите другую опцию")
        return VIN_OR_STS

async def get_engine_volume(update: Update, context: CallbackContext):
    if update.message.text == '📝 Другой объем':
        await update.message.reply_text("⚙️ *Введите объем двигателя:* (например: 1.4 или 2.0)", 
                                      parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return ENGINE_VOLUME
    else:
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
    context.user_data['fuel_type'] = update.message.text
    if context.user_data.get('editing'):
        del context.user_data['editing']
        return await show_summary(update, context)
    else:
        return await ask_parts(update, context)

async def ask_parts(update: Update, context: CallbackContext):
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
    context.user_data['current_part']['details'] = update.message.text
    return await ask_part_photo(update, context)

async def ask_part_photo(update: Update, context: CallbackContext):
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
    keyboard = [['✅ Добавить еще'], ['❌ Это все']]
    count = len(context.user_data['parts'])
    await update.message.reply_text(
        f"📦 Добавлено {count} запчастей\n\nДобавить еще?", 
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return MORE_PARTS

async def handle_more_parts(update: Update, context: CallbackContext):
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
    data = context.user_data
    text = f"📋 *СВОДКА ЗАКАЗА*\n\n📍 *Город:* {data['city']}\n🚗 *Авто:* {data['car_brand']} {data['car_model']} {data['car_year']}\n"
    
    if not data.get('vin_skipped', True):
        if data.get('vin_text'):
            text += f"🔢 *вин/стс:* {data['vin_text']}\n"
        elif data.get('vin_photo'):
            text += f"🔢 *вин/стс:* 📷 (есть фото)\n"
    else:
        text += f"⚙️ *Двигатель:* {data.get('engine_volume', '')} {data.get('fuel_type', '')}\n"
    
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
    if update.message.text == '🚀 Отправить заявку':
        # Останавливаем напоминания
        user_id = update.effective_user.id
        if user_id in user_reminders:
            for task in user_reminders[user_id]:
                task.cancel()
            del user_reminders[user_id]
        
        # Создаем ID заявки
        order_id = int(datetime.now().timestamp())
        
        try:
            # Отправляем уведомление администратору
            admin_text = f"🚨 НОВАЯ ЗАЯВКА #{order_id}\n"
            admin_text += f"📍 Город: {context.user_data['city']}\n"
            admin_text += f"🚗 Авто: {context.user_data['car_brand']} {context.user_data['car_model']} {context.user_data['car_year']}\n"
            
            if not context.user_data.get('vin_skipped', True):
                if context.user_data.get('vin_text'):
                    admin_text += f"🔢 вин/стс: {context.user_data['vin_text']}\n"
                elif context.user_data.get('vin_photo'):
                    admin_text += f"🔢 вин/стс: 📷 (фото ниже)\n"
            else:
                admin_text += f"⚙️ Двигатель: {context.user_data.get('engine_volume', '')} {context.user_data.get('fuel_type', '')}\n"
            
            admin_text += f"👤 Клиент: {context.user_data['contact_name']}\n"
            admin_text += f"📞 Тел: {context.user_data['contact_phone']}\n\n"
            admin_text += "🔧 ЗАПРОШЕННЫЕ ЗАПЧАСТИ:\n"
            
            for i, part in enumerate(context.user_data['parts'], 1):
                admin_text += f"\n{i}. {part['name']}"
                if part['details'] and part['details'] != 'Без уточнений':
                    admin_text += f"\n   Детали: {part['details']}"
                if part.get('photo'):
                    admin_text += " 📷"
            
            # Отправляем текст администратору
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
            
            # Пересылаем фото вин/стс если есть
            if context.user_data.get('vin_photo'):
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=context.user_data['vin_photo'],
                    caption=f"🆔 Фото вин/стс для заявки #{order_id}"
                )
            
            # Пересылаем фото запчастей если есть
            for i, part in enumerate(context.user_data['parts'], 1):
                if part.get('photo'):
                    await context.bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=part['photo'],
                        caption=f"🔧 Фото запчасти для заявки #{order_id}\n{part['name']}"
                    )
            
            await update.message.reply_text(
                f"🎉 *ЗАЯВКА #{order_id} ПРИНЯТА!*\n\n✅ Менеджер свяжется с вами в ближайшее время!", 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardRemove()
            )
                    
        except Exception as e:
            logger.error(f"Ошибка отправки заявки: {e}")
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
    # Останавливаем напоминания
    user_id = update.effective_user.id
    if user_id in user_reminders:
        for task in user_reminders[user_id]:
            task.cancel()
        del user_reminders[user_id]
    
    await update.message.reply_text("Диалог прерван. Напишите /start для начала нового заказа", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("❌ Ошибка: BOT_TOKEN не установлен!")
        return
    
    # Создаем Application вместо Updater
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Настраиваем обработчики
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            CAR_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_brand)],
            CAR_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_model)],
            CAR_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_car_year)],
            VIN_OR_STS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_vin_choice),
                MessageHandler(filters.PHOTO, handle_vin_photo)
            ],
            VIN_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vin_text)],
            ENGINE_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_engine_volume)],
            ENGINE_FUEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fuel_type)],
            PART_MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_part_main)],
            PART_REFINEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_part_refinement)],
            PART_SPECIFICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_part_specifics)],
            PART_PHOTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_part_photo),
                MessageHandler(filters.PHOTO, handle_part_photo)
            ],
            MORE_PARTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_more_parts)],
            CONTACT_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact_info)],
            CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation)],
            EDIT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_choice)],
        },
        fallbacks=[
            CommandHandler('start', start),
            CommandHandler('cancel', cancel)
        ]
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("🤖 Бот 'АвтоЗапчасти 24/7' запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
