import subprocess
import sys
import os

def auto_install():
    required = ["python-telegram-bot[job-queue]", "pytz", "reportlab"]
    for package in required:
        try:
            if package == "pytz":
                import pytz
            elif package == "reportlab":
                import reportlab
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import pytz
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO

DATA_FILE = "schedule.json"
STUDENTS_FILE = "students.json"
GROUPS_FILE = "groups.json"
SETTINGS_FILE = "settings.json"
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

def load_groups():
    return load_json(GROUPS_FILE)

def save_groups(groups):
    save_json(GROUPS_FILE, groups)

def load_settings():
    default = {"reminder_minutes": 60, "zoom_link": ""}
    data = load_json(SETTINGS_FILE, default)
    if "zoom_link" not in data:
        data["zoom_link"] = ""
        save_settings(data)
    return data

def save_settings(settings):
    save_json(SETTINGS_FILE, settings)

def load_slots():
    default_slots = [f"{h:02d}:00" for h in range(10, 19)]
    data = load_json(SLOTS_FILE, default_slots)
    if not data or not isinstance(data, list) or len(data) != 9:
        data = default_slots
        save_json(SLOTS_FILE, data)
    return sorted(data)

def save_slots(slots):
    save_json(SLOTS_FILE, sorted(slots))

def get_schedule_keyboard(day_index, week_offset=0):
    schedule = load_schedule()
    slots = load_slots()
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    target_date = start_of_week + datetime.timedelta(days=day_index + week_offset * 7)
    key = target_date.strftime("%Y-%m-%d")
    
    lessons = schedule.get(key, [])
    lessons.sort(key=lambda x: x.get("time", "00:00"))
    
    buttons = []
    
    for slot in slots:
        row = []
        row.append(InlineKeyboardButton(slot, callback_data=f"edit_time_{key}_{slot}"))
        
        lesson = None
        for l in lessons:
            if l.get("time") == slot:
                lesson = l
                break
        
        if lesson:
            student = lesson.get("student", "Неизвестно")
            row.append(InlineKeyboardButton(student, callback_data=f"edit_student_{key}_{slot}"))
            reminder = lesson.get("reminder_minutes", 60)
            if reminder > 0:
                row.append(InlineKeyboardButton("🔔✅", callback_data=f"edit_reminder_{key}_{slot}"))
            else:
                row.append(InlineKeyboardButton("🔕❌", callback_data=f"edit_reminder_{key}_{slot}"))
            row.append(InlineKeyboardButton("🗑", callback_data=f"delete_lesson_{key}_{slot}"))
        else:
            row.append(InlineKeyboardButton("➕", callback_data=f"add_slot_{key}_{slot}"))
            row.append(InlineKeyboardButton(" ", callback_data="empty"))
            row.append(InlineKeyboardButton(" ", callback_data="empty"))
        
        buttons.append(row)
    
    day_buttons = []
    for i, day in enumerate(days):
        if i == day_index:
            day_buttons.append(InlineKeyboardButton(f"✅{day}", callback_data=f"day_{i}_{week_offset}"))
        else:
            day_buttons.append(InlineKeyboardButton(day, callback_data=f"day_{i}_{week_offset}"))
    
    nav_buttons = [
        InlineKeyboardButton("◀", callback_data=f"week_{week_offset-1}"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
        InlineKeyboardButton("▶", callback_data=f"week_{week_offset+1}")
    ]
    
    action_buttons = [
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    ]
    
    keyboard = [day_buttons] + buttons + [nav_buttons] + [action_buttons]
    return InlineKeyboardMarkup(keyboard)

def get_students_keyboard():
    students = load_students()
    groups = load_groups()
    buttons = []
    
    for student_id, name in students.items():
        if len(name) > 20:
            name = name[:18] + "…"
        buttons.append([InlineKeyboardButton(f"👤 {name}", callback_data=f"student_{student_id}_{name}")])
    
    for group_name, members in groups.items():
        if len(group_name) > 20:
            group_name = group_name[:18] + "…"
        buttons.append([InlineKeyboardButton(f"👥 {group_name}", callback_data=f"group_{group_name}")])
    
    buttons.append([InlineKeyboardButton("✏️ Вручную", callback_data="manual_add")])
    buttons.append([InlineKeyboardButton("➕ Создать группу", callback_data="create_group")])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    
    return InlineKeyboardMarkup(buttons)

def get_time_picker_keyboard(key, old_time):
    """Выбор нового времени для слота — только целые часы, с +5/-5"""
    buttons = []
    # Кнопки целых часов
    row = []
    for h in range(9, 23):
        time_str = f"{h:02d}:00"
        row.append(InlineKeyboardButton(time_str, callback_data=f"set_time_{key}_{old_time}_{time_str}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Кнопки +5 и -5
    current_hour = int(old_time.split(":")[0])
    current_min = int(old_time.split(":")[1])
    
    prev_min = (current_min - 5) % 60
    prev_hour = current_hour - 1 if current_min - 5 < 0 else current_hour
    if prev_hour < 9:
        prev_hour = 9
    prev_time = f"{prev_hour:02d}:{prev_min:02d}"
    
    next_min = (current_min + 5) % 60
    next_hour = current_hour + 1 if current_min + 5 >= 60 else current_hour
    if next_hour > 23:
        next_hour = 23
    next_time = f"{next_hour:02d}:{next_min:02d}"
    
    buttons.append([
        InlineKeyboardButton("➖ 5", callback_data=f"set_time_{key}_{old_time}_{prev_time}"),
        InlineKeyboardButton(f"🕐 {old_time}", callback_data="empty"),
        InlineKeyboardButton("➕ 5", callback_data=f"set_time_{key}_{old_time}_{next_time}")
    ])
    
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    return InlineKeyboardMarkup(buttons)

def get_reminder_picker_keyboard(key, time):
    buttons = [
        [InlineKeyboardButton("5 мин", callback_data=f"set_reminder_{key}_{time}_5")],
        [InlineKeyboardButton("15 мин", callback_data=f"set_reminder_{key}_{time}_15")],
        [InlineKeyboardButton("30 мин", callback_data=f"set_reminder_{key}_{time}_30")],
        [InlineKeyboardButton("60 мин", callback_data=f"set_reminder_{key}_{time}_60")],
        [InlineKeyboardButton("120 мин", callback_data=f"set_reminder_{key}_{time}_120")],
        [InlineKeyboardButton("❌ Отключить", callback_data=f"set_reminder_{key}_{time}_0")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_schedule")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_settings_keyboard():
    settings = load_settings()
    current = settings.get("reminder_minutes", 60)
    zoom_link = settings.get("zoom_link", "")
    zoom_status = "🔗 Есть" if zoom_link else "🔗 Нет"
    buttons = [
        [InlineKeyboardButton(f"⏰ Напомнить за {current} мин", callback_data="settings_show")],
        [InlineKeyboardButton("➖ 5 мин", callback_data="set_dec"), 
         InlineKeyboardButton("➕ 5 мин", callback_data="set_inc")],
        [InlineKeyboardButton(zoom_status, callback_data="settings_zoom")],
        [InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_zoom_keyboard(zoom_link):
    buttons = []
    if zoom_link:
        buttons.append([InlineKeyboardButton("✏️ Изменить", callback_data="zoom_edit")])
        buttons.append([InlineKeyboardButton("🗑 Удалить", callback_data="zoom_delete")])
    else:
        buttons.append([InlineKeyboardButton("➕ Добавить", callback_data="zoom_add")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def format_schedule(day_index, week_offset=0):
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    day_name = days[day_index]
    
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    target_date = start_of_week + datetime.timedelta(days=day_index + week_offset * 7)
    
    date_str = target_date.strftime("%d.%m")
    
    today_key = today.strftime("%Y-%m-%d")
    key = target_date.strftime("%Y-%m-%d")
    is_today = key == today_key
    
    if is_today:
        header = f"📅 СЕГОДНЯ {date_str}"
    elif week_offset == 0:
        header = f"📅 {day_name} {date_str}"
    else:
        header = f"📅 {day_name} {date_str}"
    
    return header

async def show_schedule(update_or_query, context, text_prefix=""):
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    day_index = context.user_data.get('selected_day', today.weekday())
    week_offset = context.user_data.get('week_offset', 0)
    
    text = format_schedule(day_index, week_offset)
    keyboard = get_schedule_keyboard(day_index, week_offset)
    
    full_text = f"{text_prefix}\n\n{text}" if text_prefix else text
    
    if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
        await update_or_query.callback_query.edit_message_text(
            full_text,
            reply_markup=keyboard,
            parse_mode=None
        )
    elif hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(
            full_text,
            reply_markup=keyboard,
            parse_mode=None
        )
    else:
        try:
            await update_or_query.message.reply_text(
                full_text,
                reply_markup=keyboard,
                parse_mode=None
            )
        except:
            pass

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "today":
        today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        day_index = today.weekday()
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = 0
        await show_schedule(query, context)
        return
    
    if data.startswith("day_"):
        parts = data.split("_")
        day_index = int(parts[1])
        week_offset = int(parts[2])
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = week_offset
        await show_schedule(query, context)
        return
    
    if data.startswith("week_"):
        week_offset = int(data.split("_")[1])
        context.user_data['week_offset'] = week_offset
        day_index = context.user_data.get('selected_day', 0)
        await show_schedule(query, context)
        return
    
    if data.startswith("add_slot_"):
        parts = data.split("_")
        key = parts[2]
        slot_time = parts[3]
        
        context.user_data["selected_key"] = key
        context.user_data["selected_slot"] = slot_time
        
        students = load_students()
        if not students:
            await query.edit_message_text("❌ Нет учеников. Нажми 'Вручную' и добавь.", parse_mode=None)
            return
        
        keyboard = get_students_keyboard()
        await query.edit_message_text(
            "👤 Выбери ученика для слота:",
            reply_markup=keyboard,
            parse_mode=None
        )
        context.user_data["waiting_for_student"] = True
        return
    
    if data.startswith("student_"):
        parts = data.split("_")
        student_id = parts[1]
        student_name = "_".join(parts[2:])
        
        key = context.user_data.get("selected_key")
        slot_time = context.user_data.get("selected_slot")
        
        if key and slot_time:
            schedule = load_schedule()
            if key not in schedule:
                schedule[key] = []
            
            for lesson in schedule[key]:
                if lesson.get("time") == slot_time:
                    await query.edit_message_text(f"❌ Слот {slot_time} уже занят!", parse_mode=None)
                    return
            
            schedule[key].append({
                "time": slot_time,
                "student": student_name,
                "student_id": student_id,
                "topic": "-",
                "reminded": False,
                "zoom_link": "",
                "reminder_minutes": 60
            })
            save_schedule(schedule)
            context.user_data.pop("selected_key", None)
            context.user_data.pop("selected_slot", None)
            context.user_data.pop("waiting_for_student", None)
            
            await query.edit_message_text(f"✅ {student_name} на {slot_time}!")
            await show_schedule(query, context)
            return
        
        context.user_data["selected_student"] = {"id": student_id, "name": student_name}
        await query.edit_message_text(
            f"👤 {student_name}\n\n📅 Выбери дату:",
            reply_markup=get_date_keyboard(0),
            parse_mode=None
        )
        context.user_data.pop("waiting_for_student", None)
        return
    
    if data.startswith("group_"):
        group_name = data.replace("group_", "")
        key = context.user_data.get("selected_key")
        slot_time = context.user_data.get("selected_slot")
        
        if key and slot_time:
            schedule = load_schedule()
            if key not in schedule:
                schedule[key] = []
            
            groups = load_groups()
            students = load_students()
            added = 0
            
            for name in groups.get(group_name, []):
                student_id = None
                for sid, sname in students.items():
                    if sname == name:
                        student_id = sid
                        break
                if student_id:
                    schedule[key].append({
                        "time": slot_time,
                        "student": name,
                        "student_id": student_id,
                        "topic": "-",
                        "reminded": False,
                        "zoom_link": "",
                        "reminder_minutes": 60
                    })
                    added += 1
            
            if added == 0:
                await query.edit_message_text(f"❌ В группе '{group_name}' нет учеников с ID!", parse_mode=None)
                return
            
            save_schedule(schedule)
            context.user_data.pop("selected_key", None)
            context.user_data.pop("selected_slot", None)
            
            await query.edit_message_text(f"✅ Добавлено {added} учеников из группы '{group_name}' на {slot_time}!")
            await show_schedule(query, context)
            return
    
    if data.startswith("edit_time_"):
        parts = data.split("_")
        key = parts[2]
        old_time = "_".join(parts[3:])
        
        keyboard = get_time_picker_keyboard(key, old_time)
        await query.edit_message_text(
            f"🕐 Выбери новое время для {old_time}:",
            reply_markup=keyboard,
            parse_mode=None
        )
        return
    
    if data.startswith("set_time_"):
        parts = data.split("_")
        key = parts[2]
        old_time = "_".join(parts[3:-1])
        new_time = parts[-1]
        
        schedule = load_schedule()
        if key in schedule:
            for i, lesson in enumerate(schedule[key]):
                if lesson.get("time") == old_time:
                    for j, l in enumerate(schedule[key]):
                        if l.get("time") == new_time and j != i:
                            await query.edit_message_text(f"❌ Время {new_time} уже занято!", parse_mode=None)
                            return
                    lesson["time"] = new_time
                    schedule[key] = sorted(schedule[key], key=lambda x: x.get("time", "00:00"))
                    save_schedule(schedule)
                    await query.edit_message_text(f"✅ Время изменено: {old_time} → {new_time}", parse_mode=None)
                    await show_schedule(query, context)
                    return
        
        await query.edit_message_text("❌ Занятие не найдено", parse_mode=None)
        return
    
    if data.startswith("edit_student_"):
        parts = data.split("_")
        key = parts[2]
        time = "_".join(parts[3:])
        
        context.user_data["edit_student_key"] = key
        context.user_data["edit_student_time"] = time
        
        students = load_students()
        keyboard = get_students_keyboard()
        await query.edit_message_text(
            f"👤 Выбери нового ученика для {time}:",
            reply_markup=keyboard,
            parse_mode=None
        )
        context.user_data["waiting_for_student"] = True
        return
    
    if data.startswith("edit_reminder_"):
        parts = data.split("_")
        key = parts[2]
        time = "_".join(parts[3:])
        
        keyboard = get_reminder_picker_keyboard(key, time)
        await query.edit_message_text(
            f"🔔 Выбери время напоминания для {time}:",
            reply_markup=keyboard,
            parse_mode=None
        )
        return
    
    if data.startswith("set_reminder_"):
        parts = data.split("_")
        key = parts[2]
        time = "_".join(parts[3:-1])
        minutes = int(parts[-1])
        
        schedule = load_schedule()
        if key in schedule:
            for lesson in schedule[key]:
                if lesson.get("time") == time:
                    lesson["reminder_minutes"] = minutes
                    save_schedule(schedule)
                    await query.edit_message_text(
                        f"✅ Напоминание для {time} установлено на {minutes} мин!" if minutes > 0 else "✅ Напоминание отключено!",
                        parse_mode=None
                    )
                    await show_schedule(query, context)
                    return
        
        await query.edit_message_text("❌ Занятие не найдено", parse_mode=None)
        return
    
    if data.startswith("delete_lesson_"):
        parts = data.split("_")
        key = parts[2]
        time = "_".join(parts[3:])
        
        schedule = load_schedule()
        if key in schedule:
            original_len = len(schedule[key])
            schedule[key] = [l for l in schedule[key] if l.get("time") != time]
            if len(schedule[key]) < original_len:
                if not schedule[key]:
                    del schedule[key]
                save_schedule(schedule)
                await query.edit_message_text("✅ Удалено!", parse_mode=None)
                await show_schedule(query, context)
                return
        
        await query.edit_message_text("❌ Занятие не найдено", parse_mode=None)
        return
    
    if data == "settings":
        keyboard = get_settings_keyboard()
        await query.edit_message_text("⚙️ Настройки\n\nВыбери действие:", reply_markup=keyboard, parse_mode=None)
        return
    
    if data == "settings_back":
        await show_schedule(query, context)
        return
    
    if data == "settings_show":
        settings = load_settings()
        current = settings.get("reminder_minutes", 60)
        await query.edit_message_text(
            f"⏰ Текущее время напоминания: {current} мин\n\nИзменить можно кнопками ниже:",
            reply_markup=get_settings_keyboard(),
            parse_mode=None
        )
        return
    
    if data == "set_inc":
        settings = load_settings()
        current = settings.get("reminder_minutes", 60)
        new_val = min(current + 5, 1440)
        settings["reminder_minutes"] = new_val
        save_settings(settings)
        await query.edit_message_text(
            f"⏰ Напоминание установлено на {new_val} мин!\n\nИзменить можно кнопками ниже:",
            reply_markup=get_settings_keyboard(),
            parse_mode=None
        )
        return
    
    if data == "set_dec":
        settings = load_settings()
        current = settings.get("reminder_minutes", 60)
        new_val = max(current - 5, 5)
        settings["reminder_minutes"] = new_val
        save_settings(settings)
        await query.edit_message_text(
            f"⏰ Напоминание установлено на {new_val} мин!\n\nИзменить можно кнопками ниже:",
            reply_markup=get_settings_keyboard(),
            parse_mode=None
        )
        return
    
    if data == "settings_zoom":
        settings = load_settings()
        zoom_link = settings.get("zoom_link", "")
        keyboard = get_zoom_keyboard(zoom_link)
        
        if zoom_link:
            text = f"🔗 Ссылка на конференцию:\n\n{zoom_link}"
        else:
            text = "🔗 Ссылка на конференцию не установлена.\n\nНажми 'Добавить', чтобы вставить ссылку."
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=None, disable_web_page_preview=True)
        return
    
    if data == "zoom_add" or data == "zoom_edit":
        context.user_data["waiting_for_zoom"] = True
        await query.edit_message_text(
            "🔗 Вставь ссылку на конференцию (Zoom, Meet и т.д.):\n\n"
            "Например: https://zoom.us/j/123456789",
            parse_mode=None
        )
        return
    
    if data == "zoom_delete":
        settings = load_settings()
        settings["zoom_link"] = ""
        save_settings(settings)
        await query.edit_message_text("✅ Ссылка удалена!", parse_mode=None)
        keyboard = get_settings_keyboard()
        await query.edit_message_text("⚙️ Настройки\n\nВыбери действие:", reply_markup=keyboard, parse_mode=None)
        return
    
    if data == "manual_add":
        await query.edit_message_text("✏️ Введи имя ученика:", parse_mode=None)
        context.user_data["waiting_for_manual"] = True
        return
    
    if data == "create_group":
        await query.edit_message_text("👥 Создание группы\n\nВведи название группы:", parse_mode=None)
        context.user_data["waiting_for_group_name"] = True
        return
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Отменено", parse_mode=None)
        context.user_data.clear()
        await show_schedule(query, context)
        return
    
    if data == "empty":
        return

def get_date_keyboard(month_offset=0):
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    target_month = today.month + month_offset
    target_year = today.year
    while target_month > 12:
        target_month -= 12
        target_year += 1
    while target_month < 1:
        target_month += 12
        target_year -= 1
    
    first_day = datetime.datetime(target_year, target_month, 1)
    if target_month == 12:
        last_day = datetime.datetime(target_year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.datetime(target_year, target_month + 1, 1) - datetime.timedelta(days=1)
    
    start_weekday = first_day.weekday()
    
    buttons = []
    month_names = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                   "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    buttons.append([InlineKeyboardButton(
        f"📅 {month_names[target_month-1]} {target_year}",
        callback_data="month_title"
    )])
    
    weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    buttons.append([InlineKeyboardButton(day, callback_data="weekday") for day in weekdays])
    
    row = []
    for _ in range(start_weekday):
        row.append(InlineKeyboardButton(" ", callback_data="empty"))
    
    current_date = first_day
    while current_date <= last_day:
        day_str = current_date.strftime("%d.%m.%Y")
        day_display = str(current_date.day)
        row.append(InlineKeyboardButton(day_display, callback_data=f"date_{day_str}"))
        
        if len(row) == 7:
            buttons.append(row)
            row = []
        current_date += datetime.timedelta(days=1)
    
    if row:
        while len(row) < 7:
            row.append(InlineKeyboardButton(" ", callback_data="empty"))
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton("◀", callback_data=f"month_{month_offset-1}"),
        InlineKeyboardButton("📅 Сегодня", callback_data="month_today"),
        InlineKeyboardButton("▶", callback_data=f"month_{month_offset+1}")
    ])
    
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    
    return InlineKeyboardMarkup(buttons)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_zoom"):
        link = update.message.text.strip()
        if not link:
            await update.message.reply_text("❌ Ссылка не может быть пустой")
            return
        
        settings = load_settings()
        settings["zoom_link"] = link
        save_settings(settings)
        context.user_data.pop("waiting_for_zoom", None)
        
        await update.message.reply_text(f"✅ Ссылка на конференцию сохранена!")
        keyboard = get_settings_keyboard()
        await update.message.reply_text("⚙️ Настройки", reply_markup=keyboard)
        return
    
    if context.user_data.get("waiting_for_manual"):
        await handle_manual_input(update, context)
        return
    
    if context.user_data.get("waiting_for_group_name"):
        await handle_group_name(update, context)
        return
    
    if context.user_data.get("waiting_for_group_members"):
        await handle_group_members(update, context)
        return

async def handle_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ Имя не может быть пустым")
        return
    
    user_id = f"manual_{datetime.datetime.now().timestamp()}"
    students = load_students()
    students[user_id] = name
    save_students(students)
    context.user_data.pop("waiting_for_manual", None)
    
    await update.message.reply_text(f"✅ {name} добавлен в список!")
    
    key = context.user_data.get("selected_key")
    slot_time = context.user_data.get("selected_slot")
    
    if key and slot_time:
        schedule = load_schedule()
        if key not in schedule:
            schedule[key] = []
        
        for lesson in schedule[key]:
            if lesson.get("time") == slot_time:
                await update.message.reply_text(f"❌ Слот {slot_time} уже занят!")
                return
        
        schedule[key].append({
            "time": slot_time,
            "student": name,
            "student_id": user_id,
            "topic": "-",
            "reminded": False,
            "zoom_link": "",
            "reminder_minutes": 60
        })
        save_schedule(schedule)
        context.user_data.pop("selected_key", None)
        context.user_data.pop("selected_slot", None)
        
        await update.message.reply_text(f"✅ {name} на {slot_time}!")
        await show_schedule(update, context)
    else:
        keyboard = get_students_keyboard()
        await update.message.reply_text(
            "👤 Теперь выбери ученика для слота:",
            reply_markup=keyboard
        )
        context.user_data["waiting_for_student"] = True

async def handle_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_group_name"):
        return
    group_name = update.message.text.strip()
    groups = load_groups()
    if group_name in groups:
        await update.message.reply_text(f"❌ Группа '{group_name}' уже существует!")
        context.user_data.pop("waiting_for_group_name", None)
        return
    groups[group_name] = []
    save_groups(groups)
    await update.message.reply_text(f"✅ Группа '{group_name}' создана!\n\nВведи имена учеников через запятую:\n`Иванов, Петров, Сидорова`", parse_mode='Markdown')
    context.user_data["waiting_for_group_members"] = group_name

async def handle_group_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_name = context.user_data.get("waiting_for_group_members")
    if not group_name:
        return
    names = [n.strip() for n in update.message.text.split(',')]
    groups = load_groups()
    students = load_students()
    for name in names:
        if name not in groups[group_name]:
            groups[group_name].append(name)
        exists = any(s == name for s in students.values())
        if not exists:
            students[f"manual_{datetime.datetime.now().timestamp()}"] = name
    save_groups(groups)
    save_students(students)
    await update.message.reply_text(f"✅ В группу '{group_name}' добавлены:\n{', '.join(names)}")
    await show_schedule(update, context)
    context.user_data.pop("waiting_for_group_members", None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or "Пользователь"
    
    students = load_students()
    if user_id not in students:
        students[user_id] = first_name
        save_students(students)
        await update.message.reply_text(f"✅ {first_name}, ты зарегистрирован!")
    else:
        await update.message.reply_text(f"👋 С возвращением, {first_name}!")
    
    commands = [
        BotCommand("schedule", "📅 Расписание"),
        BotCommand("week", "📊 Неделя"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("export", "📄 Экспорт PDF")
    ]
    await context.bot.set_my_commands(commands)
    
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    context.user_data['selected_day'] = today.weekday()
    context.user_data['week_offset'] = 0
    
    await show_schedule(update, context)

async def show_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_schedule(update, context)

async def show_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    
    text = "📊 РАСПИСАНИЕ НА НЕДЕЛЮ\n\n"
    total = 0
    
    for i, day in enumerate(days):
        target_date = start_of_week + datetime.timedelta(days=i)
        key = target_date.strftime("%Y-%m-%d")
        lessons = load_schedule().get(key, [])
        count = len(lessons)
        total += count
        
        emoji = "✅" if count > 0 else "⬜"
        text += f"{emoji} {day} {target_date.strftime('%d.%m')}: {count} занятий\n"
    
    text += f"\n📊 Всего: {total} занятий"
    await update.message.reply_text(text, parse_mode=None)

async def export_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Генерирую PDF...")
    try:
        pdf_buffer = generate_week_pdf()
        today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        filename = f"расписание_{today.strftime('%d.%m')}.pdf"
        await update.message.reply_document(document=pdf_buffer, filename=filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_settings_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "⚙️ Настройки\n\nВыбери действие:",
            reply_markup=keyboard,
            parse_mode=None
        )
    else:
        await update.message.reply_text("⚙️ Настройки", reply_markup=keyboard)

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    default_reminder = settings.get("reminder_minutes", 60)
    zoom_link = settings.get("zoom_link", "")
    
    schedule = load_schedule()
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    today_key = now.strftime("%Y-%m-%d")
    
    for lesson in schedule.get(today_key, []):
        lesson_time = lesson.get("time", "00:00")
        try:
            h, m = map(int, lesson_time.split(":"))
            lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff = (lesson_dt - now).total_seconds() / 60
            
            reminder = lesson.get("reminder_minutes", default_reminder)
            if reminder == 0:
                continue
            
            if not lesson.get("reminded", False):
                if (reminder - 5) <= diff <= (reminder + 5):
                    student = lesson.get("student", "Ученик")
                    topic = lesson.get("topic", "занятие")
                    student_id = lesson.get("student_id")
                    
                    if student_id:
                        try:
                            message = f"⏰ Напоминание!\nЧерез {reminder} мин. занятие:\n👤 {student}\n📚 {topic}\n🕐 {lesson_time}"
                            if zoom_link:
                                message += f"\n🔗 Ссылка на конференцию:\n{zoom_link}"
                            await context.bot.send_message(
                                chat_id=int(student_id),
                                text=message,
                                disable_web_page_preview=True
                            )
                            lesson["reminded"] = True
                            save_schedule(schedule)
                        except:
                            pass
        except:
            pass

def generate_week_pdf():
    schedule = load_schedule()
    slots = load_slots()
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    week_data = []
    max_lessons = 0
    
    for i, day in enumerate(days):
        current_date = start_of_week + datetime.timedelta(days=i)
        key = current_date.strftime("%Y-%m-%d")
        date_str = current_date.strftime("%d.%m")
        lessons = schedule.get(key, [])
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        cell_lines = [f"{day} {date_str}"]
        
        if lessons:
            for lesson in lessons:
                time = lesson.get("time", "00:00")
                student = lesson.get("student", "Неизвестно")
                topic = lesson.get("topic", "-")
                line = f"{time} {student}"
                if topic != "-":
                    line += f"\n   {topic}"
                cell_lines.append(line)
            if len(lessons) > max_lessons:
                max_lessons = len(lessons)
        else:
            cell_lines.append("Нет занятий")
            if 1 > max_lessons:
                max_lessons = 1
        
        week_data.append(cell_lines)
    
    row_count = max_lessons + 1
    for day_cells in week_data:
        while len(day_cells) < row_count:
            day_cells.append("")
    
    table_data = []
    header_row = []
    for day_cells in week_data:
        header_row.append(day_cells[0])
    table_data.append(header_row)
    
    for row_idx in range(1, row_count):
        row = []
        for day_idx in range(7):
            cell_text = week_data[day_idx][row_idx] if row_idx < len(week_data[day_idx]) else ""
            row.append(cell_text)
        table_data.append(row)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                           leftMargin=20, rightMargin=20,
                           topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        backColor=colors.grey,
        spaceAfter=2,
        spaceBefore=2
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        spaceAfter=1,
        spaceBefore=1
    )
    
    elements = []
    
    date_range = f"{start_of_week.strftime('%d.%m')} – {(start_of_week + datetime.timedelta(days=6)).strftime('%d.%m.%Y')}"
    title = Paragraph(f"<b>РАСПИСАНИЕ НА НЕДЕЛЮ</b><br/>{date_range}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 10))
    
    styled_data = []
    for row_idx, row in enumerate(table_data):
        styled_row = []
        for cell_text in row:
            if row_idx == 0:
                styled_row.append(Paragraph(cell_text, header_style))
            else:
                if cell_text.strip():
                    html_text = cell_text.replace('\n', '<br/>')
                    styled_row.append(Paragraph(html_text, cell_style))
                else:
                    styled_row.append("")
        styled_data.append(styled_row)
    
    col_widths = [doc.width / 7] * 7
    
    table = Table(styled_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return buffer

def main():
    TOKEN = os.getenv("SCHEDULE_BOT_TOKEN")
    if not TOKEN:
        print("❌ SCHEDULE_BOT_TOKEN не найден!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", show_schedule_command))
    app.add_handler(CommandHandler("week", show_week))
    app.add_handler(CommandHandler("settings", settings_menu))
    app.add_handler(CommandHandler("export", export_week))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(check_reminders, interval=60, first=10)
            print("✅ Напоминания включены")
        else:
            print("ℹ️ JobQueue не доступен")
    except Exception as e:
        print(f"⚠️ Ошибка JobQueue: {e}")
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
