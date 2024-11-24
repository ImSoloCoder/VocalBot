# Токен вашего бота
# TOKEN = '7763615801:AAFizJy48WSZdmoXOO-Q7pR8Xqu4F7KWUKw'
# ADMIN_ID = 1166609863  # Замените на ваш Telegram ID

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import sqlite3
import datetime
import asyncio
from datetime import timedelta




# Подключение к базе данных SQLite
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы, если она не существует
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    name TEXT,
    phone TEXT
)
''')
conn.commit()

# Токен вашего бота
TOKEN = '7763615801:AAFizJy48WSZdmoXOO-Q7pR8Xqu4F7KWUKw'
ADMIN_ID = 462862390  # Укажите свой Telegram ID

# Создание объекта приложения и планировщика задач
app = Application.builder().token(TOKEN).build()
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.start()

# Словарь для временного хранения данных администратора
admin_task = {}

def schedule_async_task(coroutine, *args):
    asyncio.run(coroutine(*args))

# Команда /start с кнопками
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Регистрация", callback_data="register")],
        [InlineKeyboardButton("Удалить данные", callback_data="unregister")]
    ]

    reply_keyboard = [[KeyboardButton("Меню")]]  # Можно добавить другие кнопки

    # Отправляем сообщение с клавиатурой
    await update.message.reply_text(
        "Добро пожаловать!",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            resize_keyboard=True,  # Автоматическая подгонка размеров кнопок
            one_time_keyboard=False  # Клавиатура будет постоянной
        )
    )

    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Список учеников", callback_data="list_users")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# Обработчик нажатия на кнопку "Меню"
async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, если текст сообщения совпадает с "Меню"
    if update.message.text.strip() == "Меню":  # Убираем лишние пробелы
        await start(update, context)  # Вызываем обработчик /start

# Обработчик для нажатий на кнопки
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "register":
        user_id = query.from_user.id

        # Проверяем, есть ли пользователь в базе данных
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()

        if user:
            await query.message.reply_text(
                f"Вы уже зарегистрированы как {user[4]}! Чтобы зарегистрироваться заново, удалите ваши данные."
            )
        else:
            await query.message.reply_text("Введите ваше имя:")
            context.user_data['state'] = 'waiting_for_name'

    elif query.data == "unregister":
        await unregister_user(query, context)

    elif query.data == "list_users":
        await list_users_for_admin(query, context)

    elif query.data.startswith("send_to_user_"):
        await request_schedule_details(query, context)

    elif query.data in ["confirm_schedule", "edit_schedule"]:
        await handle_schedule_confirmation(query, context)

# Удаление данных пользователя
async def unregister_user(query: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    await query.message.reply_text("Ваши данные успешно удалены!")

# Список пользователей для администратора
async def list_users_for_admin(query: Update, context: ContextTypes.DEFAULT_TYPE):
    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("Эта команда доступна только администратору!")
        return

    cursor.execute('SELECT user_id, name FROM users')
    users = cursor.fetchall()

    if users:
        keyboard = [
            [InlineKeyboardButton(user[1], callback_data=f"send_to_user_{user[0]}")]
            for user in users
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите ученика для назначения урока:", reply_markup=reply_markup)
    else:
        await query.message.reply_text("Пользователи не найдены.")

# Запрос данных о встрече
async def request_schedule_details(query: Update, context: ContextTypes.DEFAULT_TYPE):
    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("Эта команда доступна только администратору!")
        return

    user_id = int(query.data.split("_")[-1])
    admin_task[query.from_user.id] = {'user_id': user_id, 'step': 'waiting_for_date'}
    await query.message.reply_text("Введите дату встречи (в формате ДД.ММ.ГГГГ):")

# Подтверждение или исправление данных
async def handle_schedule_confirmation(query: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = query.from_user.id

    if admin_id not in admin_task:
        await query.answer("Нет данных для подтверждения.")
        return

    task = admin_task[admin_id]

    if query.data == "confirm_schedule":
        user_id = task['user_id']

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Вам назначен урок по вокалу:\nДата: {task['date']}\nВремя: {task['time']}\nКабинет: {task['room']}"
            )

            meeting_datetime = datetime.datetime.strptime(
                f"{task['date']} {task['time']}", "%d.%m.%Y %H:%M"
            )
            # Это если нужно за минуту напомнить
            #reminder_time = meeting_datetime - datetime.timedelta(minutes=1)

            # Рассчитываем время напоминания (10 утра предыдущего дня)
            reminder_time = (meeting_datetime - timedelta(days=1)).replace(hour=11, minute=35, second=0)

            scheduler.add_job(
                schedule_async_task,
                trigger=DateTrigger(run_date=reminder_time),
                args=(send_reminder, user_id, task['date'], task['time'], task['room'], context)
            )

            await query.message.reply_text("Данные отправлены ученику и напоминание установлено!")
        except Exception as e:
            await query.message.reply_text(f"Ошибка при отправке сообщения: {e}")

        del admin_task[admin_id]

    elif query.data == "edit_schedule":
        task['step'] = 'waiting_for_date'
        await query.message.reply_text("Введите новую дату урока (в формате ДД.ММ.ГГГГ):")

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    # Проверяем состояние регистрации
    if context.user_data.get('state') == 'waiting_for_name':
        context.user_data['name'] = update.message.text
        context.user_data['state'] = 'waiting_for_phone'
        await update.message.reply_text("Введите ваш номер телефона:")
    elif context.user_data.get('state') == 'waiting_for_phone':
        context.user_data['phone'] = update.message.text
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, last_name, name, phone) VALUES (?, ?, ?, ?, ?, ?)',
            (
                admin_id,
                update.effective_user.username,
                update.effective_user.first_name,
                update.effective_user.last_name,
                context.user_data['name'],
                context.user_data['phone']
            )
        )
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("Вы успешно зарегистрированы!")

    if admin_id in admin_task:
        task = admin_task[admin_id]


        if task['step'] == 'waiting_for_date':
            task['date'] = update.message.text
            task['step'] = 'waiting_for_time'
            await update.message.reply_text("Введите время урока (в формате ЧЧ:ММ):")
        elif task['step'] == 'waiting_for_time':
            task['time'] = update.message.text
            task['step'] = 'waiting_for_room'
            await update.message.reply_text("Введите номер кабинета:")
        elif task['step'] == 'waiting_for_room':
            task['room'] = update.message.text

            keyboard = [
                [InlineKeyboardButton("Подтвердить", callback_data="confirm_schedule")],
                [InlineKeyboardButton("Исправить", callback_data="edit_schedule")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"Проверьте введённые данные об уроке:\nДата: {task['date']}\nВремя: {task['time']}\nКабинет: {task['room']}",
                reply_markup=reply_markup
            )

# Отправка напоминания
async def send_reminder(user_id, date, time, room, context):
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Напоминание! Завтра состоится урок по вокалу:\nДата: {date}\nВремя: {time}\nКабинет: {room}"
        )
    except Exception as e:
        print(f"Ошибка при отправке напоминания: {e}")

# Запуск задачи в планировщике


#def schedule_async_task(coroutine, *args):
   # loop = asyncio.get_event_loop()
   # asyncio.run_coroutine_threadsafe(coroutine(*args), loop)

# Регистрация обработчиков
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_button_click))
app.add_handler(MessageHandler(filters.Text("Меню"), handle_menu_button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
#app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Меню$"), handle_menu_button))



# Запуск бота
print("Бот запущен!")
app.run_polling()
