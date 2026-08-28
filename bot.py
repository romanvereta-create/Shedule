import subprocess
import sys
import os

# АВТОУСТАНОВКА БИБЛИОТЕК ПРИ ЗАПУСКЕ
def auto_install():
    required = ["python-telegram-bot[job-queue]", "pytz"]
    for package in required:
        try:
            if package == "pytz":
                import pytz
            else:
                __import__(package.split("[")[0].replace("-", "_"))
        except ImportError:
            print(f"📦 Устанавливаю {package}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "--quiet", "--disable-pip-version-check"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

auto_install()

import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import pytz

# ======================== ХРАНЕНИЕ ДАННЫХ ========================

DATA_FILE = "schedule.json"
STUDENTS_FILE = "students.json"

def load_schedule():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_schedule(schedule):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)

def load_students():
    if os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_students(students):
    with open(STUDENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(students, f, ensure_ascii=False, indent=2)

# ======================== КНОПКИ ========================

def get_day_keyboard(week_offset=0, selected_day=0):
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    buttons = []
    for i, day in enumerate(days):
        is_selected = "✅ " if i == selected_day else ""
        callback = f"day_{i}_{week_offset}"
        buttons.append(InlineKeyboardButton(f"{is_selected}{day}", callback_data=callback))
    
    nav_buttons = [
        InlineKeyboardButton("◀ Назад", callback_data=f"week_{week_offset-1}"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
        InlineKeyboardButton("Вперёд ▶", callback_data=f"week_{week_offset+1}")
    ]
    
    action_buttons = [
        InlineKeyboardButton("➕ Добавить", callback_data="add_lesson"),
        InlineKeyboardButton("🗑 Удалить", callback_data="delete_lesson")
    ]
    
    keyboard = [buttons, nav_buttons, action_buttons]
    return InlineKeyboardMarkup(keyboard)

def get_students_keyboard():
    students = load_students()
    if not students:
        return None
    
    buttons = []
    for student_id, name in students.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"student_{student_id}_{name}")])
    
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    return InlineKeyboardMarkup(buttons)

def get_date_keyboard():
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    buttons = []
    
    for i in range(7):
        date = today + datetime.timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        day_name = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][date.weekday()]
        buttons.append([InlineKeyboardButton(f"{day_name} {date_str}", callback_data=f"date_{date_str}")])
    
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    return InlineKeyboardMarkup(buttons)

def get_time_hours_keyboard():
    buttons = []
    row = []
    for h in range(9, 22):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"hour_{h}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    return InlineKeyboardMarkup(buttons)

def get_time_minutes_keyboard(hour):
    buttons = [
        [InlineKeyboardButton("00", callback_data=f"min_{hour}_00"),
         InlineKeyboardButton("15", callback_data=f"min_{hour}_15"),
         InlineKeyboardButton("30", callback_data=f"min_{hour}_30"),
         InlineKeyboardButton("45", callback_data=f"min_{hour}_45")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
    ]
    return InlineKeyboardMarkup(buttons)

# ======================== ФОРМАТИРОВАНИЕ ========================

def format_schedule(day_index, week_offset=0):
    schedule = load_schedule()
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    day_name = days[day_index]
    
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    target_date = start_of_week + datetime.timedelta(days=day_index + week_offset * 7)
    
    date_str = target_date.strftime("%d.%m.%Y")
    key = target_date.strftime("%Y-%m-%d")
    
    lessons = schedule.get(key, [])
    lessons.sort(key=lambda x: x.get("time", "00:00"))
    
    today_key = today.strftime("%Y-%m-%d")
    is_today = key == today_key
    
    if is_today:
        header = "📅 СЕГОДНЯ"
    elif week_offset == 0:
        header = f"📅 {day_name} {date_str}"
    else:
        header = f"📅 {day_name} {date_str}"
    
    if not lessons:
        return f"{header}\n\n✨ Нет занятий\n\n🎉 Свободно: весь день"
    
    text = f"{header}\n\n"
    
    for lesson in lessons:
        time = lesson.get("time", "00:00")
        student = lesson.get("student", "Неизвестно")
        topic = lesson.get("topic", "-")
        text += f"🕐 *{time}* — {student}\n"
        if topic != "-":
            text += f"   📚 {topic}\n"
        text += "\n"
    
    return text

# ======================== НАПОМИНАНИЯ ========================

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    schedule = load_schedule()
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    today_key = now.strftime("%Y-%m-%d")
    
    for lesson in schedule.get(today_key, []):
        lesson_time = lesson.get("time", "00:00")
        try:
            h, m = map(int, lesson_time.split(":"))
            lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff = (lesson_dt - now).total_seconds() / 60
            
            if 55 <= diff <= 65:
                student = lesson.get("student", "Ученик")
                topic = lesson.get("topic", "занятие")
                student_id = lesson.get("student_id")
                
                if student_id:
                    try:
                        await context.bot.send_message(
                            chat_id=int(student_id),
                            text=f"⏰ Напоминание!\nЧерез час занятие:\n👤 {student}\n📚 {topic}\n🕐 {lesson_time}"
                        )
                    except:
                        pass
        except:
            pass

# ======================== КОМАНДЫ ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or "Пользователь"
    
    students = load_students()
    if user_id not in students:
        students[user_id] = first_name
        save_students(students)
        await update.message.reply_text(f"✅ {first_name}, ты зарегистрирован как ученик!")
    else:
        await update.message.reply_text(f"👋 С возвращением, {first_name}!")
    
    await update.message.reply_text(
        "👋 Я бот-расписание.\n\n"
        "📅 Показать расписание: /schedule\n"
        "➕ Добавить занятие: /add\n"
        "🗑 Удалить занятие: /delete\n"
        "📊 Статистика: /week"
    )

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    day_index = today.weekday()
    context.user_data['selected_day'] = day_index
    context.user_data['week_offset'] = 0
    
    text = format_schedule(day_index, 0)
    await update.message.reply_text(
        text,
        reply_markup=get_day_keyboard(0, day_index),
        parse_mode='Markdown'
    )

async def show_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    
    text = "📊 *РАСПИСАНИЕ НА НЕДЕЛЮ*\n\n"
    total = 0
    
    for i, day in enumerate(days):
        target_date = start_of_week + datetime.timedelta(days=i)
        key = target_date.strftime("%Y-%m-%d")
        lessons = load_schedule().get(key, [])
        count = len(lessons)
        total += count
        
        emoji = "✅" if count > 0 else "⬜"
        text += f"{emoji} {day} {target_date.strftime('%d.%m')}: {count} занятий\n"
    
    text += f"\n📊 *Всего: {total} занятий*"
    await update.message.reply_text(text, parse_mode='Markdown')

async def add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    students = load_students()
    if not students:
        # Отправляем ответ через callback или message
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Нет зарегистрированных учеников.\n"
                "Попроси учеников написать боту `/start`"
            )
        else:
            await update.message.reply_text(
                "❌ Нет зарегистрированных учеников.\n"
                "Попроси учеников написать боту `/start`"
            )
        return
    
    keyboard = get_students_keyboard()
    text = "👤 *Выбери ученика:*"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    context.user_data["waiting_for_student"] = True

async def select_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        return
    
    if data.startswith("student_"):
        parts = data.split("_")
        student_id = parts[1]
        student_name = "_".join(parts[2:])
        
        context.user_data["selected_student"] = {
            "id": student_id,
            "name": student_name
        }
        
        await query.edit_message_text(
            f"👤 Ученик: *{student_name}*\n\n"
            "📅 *Выбери дату:*",
            reply_markup=get_date_keyboard(),
            parse_mode='Markdown'
        )
        context.user_data.pop("waiting_for_student", None)

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        return
    
    if data.startswith("date_"):
        date_str = data.replace("date_", "")
        context.user_data["selected_date"] = date_str
        
        student_name = context.user_data.get("selected_student", {}).get("name", "Ученик")
        
        await query.edit_message_text(
            f"👤 Ученик: *{student_name}*\n"
            f"📅 Дата: *{date_str}*\n\n"
            "🕐 *Выбери час:*",
            reply_markup=get_time_hours_keyboard(),
            parse_mode='Markdown'
        )

async def select_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        return
    
    if data.startswith("hour_"):
        hour = int(data.split("_")[1])
        context.user_data["selected_hour"] = hour
        
        student_name = context.user_data.get("selected_student", {}).get("name", "Ученик")
        date_str = context.user_data.get("selected_date", "Дата")
        
        await query.edit_message_text(
            f"👤 Ученик: *{student_name}*\n"
            f"📅 Дата: *{date_str}*\n"
            f"🕐 Час: *{hour:02d}:XX*\n\n"
            "🕐 *Выбери минуты:*",
            reply_markup=get_time_minutes_keyboard(hour),
            parse_mode='Markdown'
        )

async def select_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        return
    
    if data.startswith("min_"):
        parts = data.split("_")
        hour = int(parts[1])
        minute = parts[2]
        time_str = f"{hour:02d}:{minute}"
        
        student_data = context.user_data.get("selected_student")
        date_str = context.user_data.get("selected_date")
        
        if not student_data or not date_str:
            await query.edit_message_text("❌ Ошибка: данные потеряны. Попробуй /add заново")
            context.user_data.clear()
            return
        
        day, month, year = map(int, date_str.split('.'))
        key = f"{year:04d}-{month:02d}-{day:02d}"
        
        schedule = load_schedule()
        if key not in schedule:
            schedule[key] = []
        
        schedule[key].append({
            "time": time_str,
            "student": student_data["name"],
            "student_id": student_data["id"],
            "topic": "-"
        })
        
        save_schedule(schedule)
        
        await query.edit_message_text(
            f"✅ *Занятие добавлено!*\n\n"
            f"👤 Ученик: {student_data['name']}\n"
            f"📅 Дата: {date_str}\n"
            f"🕐 Время: {time_str}",
            parse_mode='Markdown'
        )
        context.user_data.clear()

async def delete_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🗑 *Удаление занятия*\n\n"
        "Введи дату и имя ученика:\n"
        "`29.08 Иван`",
        parse_mode='Markdown'
    )
    context.user_data["waiting_for_delete"] = True

async def handle_delete_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_delete"):
        return
    
    try:
        parts = update.message.text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Неверный формат. Пример: `29.08 Иван`")
            return
        
        date_str, student = parts[0], parts[1]
        day, month = map(int, date_str.split('.'))
        now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        year = now.year
        if month < now.month:
            year += 1
        target_date = datetime.datetime(year, month, day)
        key = target_date.strftime("%Y-%m-%d")
        
        schedule = load_schedule()
        if key in schedule:
            original_len = len(schedule[key])
            schedule[key] = [l for l in schedule[key] if l.get("student") != student]
            
            if len(schedule[key]) < original_len:
                if not schedule[key]:
                    del schedule[key]
                save_schedule(schedule)
                await update.message.reply_text(f"✅ Удалено занятие для {student} на {date_str}")
            else:
                await update.message.reply_text(f"❌ Не найдено занятие для {student} на {date_str}")
        else:
            await update.message.reply_text(f"❌ Занятий на {date_str} нет")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data["waiting_for_delete"] = False

# ======================== ОБРАБОТКА КНОПОК ========================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "today":
        today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        day_index = today.weekday()
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = 0
        text = format_schedule(day_index, 0)
        keyboard = get_day_keyboard(0, day_index)
        
        if query.message.text != text or query.message.reply_markup != keyboard:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        return
    
    if data.startswith("day_"):
        parts = data.split("_")
        day_index = int(parts[1])
        week_offset = int(parts[2])
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = week_offset
        text = format_schedule(day_index, week_offset)
        keyboard = get_day_keyboard(week_offset, day_index)
        
        if query.message.text != text or query.message.reply_markup != keyboard:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        return
    
    if data.startswith("week_"):
        week_offset = int(data.split("_")[1])
        context.user_data['week_offset'] = week_offset
        day_index = context.user_data.get('selected_day', 0)
        text = format_schedule(day_index, week_offset)
        keyboard = get_day_keyboard(week_offset, day_index)
        
        if query.message.text != text or query.message.reply_markup != keyboard:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        return
    
    if data == "add_lesson":
        await add_lesson(update, context)
        return
    
    if data == "delete_lesson":
        await delete_lesson(update, context)
        return
    
    if data.startswith("student_") or data == "cancel_add":
        await select_student(update, context)
        return
    
    if data.startswith("date_") or data == "cancel_add":
        await select_date(update, context)
        return
    
    if data.startswith("hour_") or data == "cancel_add":
        await select_hour(update, context)
        return
    
    if data.startswith("min_") or data == "cancel_add":
        await select_minutes(update, context)
        return

# ======================== ЗАПУСК ========================

def main():
    TOKEN = os.getenv("SCHEDULE_BOT_TOKEN")
    if not TOKEN:
        print("❌ SCHEDULE_BOT_TOKEN не найден!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", show_schedule))
    app.add_handler(CommandHandler("week", show_week))
    app.add_handler(CommandHandler("add", add_lesson))
    app.add_handler(CommandHandler("delete", delete_lesson))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_lesson))
    
    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(check_reminders, interval=60, first=10)
            print("✅ Напоминания включены")
        else:
            print("ℹ️ JobQueue не доступен")
    except Exception as e:
        print(f"⚠️ Ошибка настройки JobQueue: {e}")
    
    print("✅ БОТ РАСПИСАНИЯ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
