import os
import json
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import pytz

DATA_FILE = "schedule.json"
STUDENTS_FILE = "students.json"
SLOTS_FILE = "slots.json"

def load_json(filename, default=None):
    if default is None:
        default = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_schedule():
    return load_json(DATA_FILE)

def save_schedule(schedule):
    save_json(DATA_FILE, schedule)

def load_students():
    return load_json(STUDENTS_FILE)

def save_students(students):
    save_json(STUDENTS_FILE, students)

def load_slots():
    default = [f"{h:02d}:00" for h in range(10, 19)]
    data = load_json(SLOTS_FILE, default)
    if not data or not isinstance(data, list):
        data = default
        save_json(SLOTS_FILE, data)
    return sorted(data)

def save_slots(slots):
    save_json(SLOTS_FILE, sorted(slots))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or "Пользователь"
    
    students = load_students()
    if user_id not in students:
        students[user_id] = first_name
        save_students(students)
        print(f"✅ Новый пользователь: {first_name} (ID: {user_id})")
    
    # ВАЖНО: ЗАМЕНИТЕ URL НА ВАШ!!!
    YOUR_APP_URL = "https://ваш-сайт.netlify.app/"  # <--- ЗДЕСЬ ВАШ URL
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(url=YOUR_APP_URL))]
    ])
    await update.message.reply_text(
        f"👋 Привет, {first_name}!\n\nНажми кнопку, чтобы открыть расписание.",
        reply_markup=keyboard
    )

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от Mini App"""
    try:
        # Получаем данные
        data = json.loads(update.message.web_app_data.data)
        print(f"📥 ПОЛУЧЕН ЗАПРОС: {data}")
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return
    
    action = data.get('action')
    
    async def send_response(response):
        print(f"📤 ОТВЕТ: {response}")
        response_json = json.dumps(response, ensure_ascii=False)
        await update.message.reply_text(f"__MINIAPP_RESPONSE__{response_json}")
    
    # ===== РАСПИСАНИЕ =====
    if action == 'get_schedule':
        date = data.get('date')
        if not date:
            date = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime("%Y-%m-%d")
        
        print(f"📅 Запрос расписания для: {date}")
        
        slots = load_slots()
        schedule = load_schedule()
        lessons = schedule.get(date, [])
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        await send_response({
            "action": "get_schedule",
            "slots": slots,
            "lessons": lessons,
            "date": date
        })
        return
    
    # ===== УЧЕНИКИ =====
    if action == 'get_students':
        students = load_students()
        print(f"👥 Загружено учеников: {len(students)}")
        await send_response({
            "action": "get_students",
            "students": students
        })
        return
    
    # ===== СЛОТЫ =====
    if action == 'get_slots':
        slots = load_slots()
        await send_response({
            "action": "get_slots",
            "slots": slots
        })
        return
    
    # ===== ДОБАВИТЬ ЗАНЯТИЕ =====
    if action == 'add_lesson':
        date = data.get('date')
        time = data.get('time')
        student = data.get('student')
        student_id = data.get('student_id')
        reminder = data.get('reminder', 60)
        
        print(f"➕ Добавление: {student} на {time} ({date})")
        
        schedule = load_schedule()
        if date not in schedule:
            schedule[date] = []
        
        # Проверка на дубликат
        for lesson in schedule[date]:
            if lesson.get('time') == time:
                await send_response({
                    "action": "add_lesson", 
                    "status": "error", 
                    "message": f"Слот {time} уже занят!"
                })
                return
        
        # Добавляем
        schedule[date].append({
            "time": time,
            "student": student,
            "student_id": student_id or f"manual_{int(datetime.datetime.now().timestamp())}",
            "reminded": False,
            "reminder_minutes": reminder
        })
        save_schedule(schedule)
        print(f"✅ Занятие добавлено! Всего занятий в этот день: {len(schedule[date])}")
        
        # Возвращаем обновленное расписание
        slots = load_slots()
        lessons = schedule.get(date, [])
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        await send_response({
            "action": "add_lesson",
            "status": "ok",
            "lessons": lessons,
            "slots": slots,
            "date": date
        })
        return
    
    # ===== УДАЛИТЬ ЗАНЯТИЕ =====
    if action == 'delete_lesson':
        date = data.get('date')
        time = data.get('time')
        
        print(f"🗑 Удаление: {time} ({date})")
        
        schedule = load_schedule()
        if date in schedule:
            schedule[date] = [l for l in schedule[date] if l.get('time') != time]
            if not schedule[date]:
                del schedule[date]
            save_schedule(schedule)
        
        slots = load_slots()
        lessons = schedule.get(date, [])
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        await send_response({
            "action": "delete_lesson",
            "status": "ok",
            "lessons": lessons,
            "slots": slots,
            "date": date
        })
        return

def main():
    TOKEN = os.getenv("SCHEDULE_BOT_TOKEN")
    if not TOKEN:
        print("❌ ОШИБКА: SCHEDULE_BOT_TOKEN не найден!")
        print("Создайте .env файл или установите переменную окружения.")
        return
    
    print(f"🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    print("✅ БОТ ЗАПУЩЕН! Ожидаю запросы...")
    app.run_polling()

if __name__ == "__main__":
    main()
