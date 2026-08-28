import datetime
import os
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import pytz

# ======================== ХРАНЕНИЕ ДАННЫХ ========================

DATA_FILE = "schedule.json"

def load_schedule():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_schedule(schedule):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)

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

# ======================== ФОРМАТИРОВАНИЕ РАСПИСАНИЯ (КРАСИВО) ========================

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
    
    # Определяем, сегодня это или нет
    today_key = today.strftime("%Y-%m-%d")
    is_today = key == today_key
    
    header = "📅"
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
                student_id = lesson.get("user_id")
                
                if student_id:
                    try:
                        await context.bot.send_message(
                            chat_id=student_id,
                            text=f"⏰ Напоминание!\nЧерез час занятие:\n👤 {student}\n📚 {topic}\n🕐 {lesson_time}"
                        )
                    except:
                        pass
        except:
            pass

# ======================== КОМАНДЫ ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-расписание.\n\n"
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
    await update.message.reply_text(
        "➕ *Добавление занятия*\n\n"
        "Введи данные в формате:\n"
        "`ДД.ММ ЧЧ:ММ Имя Тема`\n\n"
        "Пример:\n"
        "`29.08 17:00 Иван Производная`",
        parse_mode='Markdown'
    )
    context.user_data["waiting_for_lesson"] = True

async def handle_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_lesson"):
        return
    
    try:
        parts = update.message.text.split(maxsplit=3)
        if len(parts) < 3:
            await update.message.reply_text("❌ Неверный формат. Пример: `29.08 17:00 Иван Производная`")
            return
        
        date_str, time_str, student = parts[0], parts[1], parts[2]
        topic = parts[3] if len(parts) > 3 else "-"
        
        day, month = map(int, date_str.split('.'))
        now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        year = now.year
        if month < now.month:
            year += 1
        target_date = datetime.datetime(year, month, day)
        key = target_date.strftime("%Y-%m-%d")
        
        schedule = load_schedule()
        if key not in schedule:
            schedule[key] = []
        
        schedule[key].append({
            "time": time_str,
            "student": student,
            "topic": topic,
            "user_id": update.effective_user.id
        })
        
        save_schedule(schedule)
        await update.message.reply_text(f"✅ Занятие добавлено!\n📅 {date_str}\n🕐 {time_str}\n👤 {student}\n📚 {topic}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data["waiting_for_lesson"] = False

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
        await query.edit_message_text(
            text,
            reply_markup=get_day_keyboard(0, day_index),
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
        await query.edit_message_text(
            text,
            reply_markup=get_day_keyboard(week_offset, day_index),
            parse_mode='Markdown'
        )
        return
    
    if data.startswith("week_"):
        week_offset = int(data.split("_")[1])
        context.user_data['week_offset'] = week_offset
        day_index = context.user_data.get('selected_day', 0)
        text = format_schedule(day_index, week_offset)
        await query.edit_message_text(
            text,
            reply_markup=get_day_keyboard(week_offset, day_index),
            parse_mode='Markdown'
        )
        return
    
    if data == "add_lesson":
        await query.message.reply_text(
            "➕ Введи данные в формате:\n"
            "`29.08 17:00 Иван Производная`",
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_lesson"] = True
        return
    
    if data == "delete_lesson":
        await query.message.reply_text(
            "🗑 Введи дату и имя:\n"
            "`29.08 Иван`",
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_delete"] = True
        return

# ======================== ЗАПУСК ========================

def main():
    import os
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
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_lesson))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_lesson))
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_reminders, interval=60, first=10)
    
    print("✅ БОТ РАСПИСАНИЯ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
