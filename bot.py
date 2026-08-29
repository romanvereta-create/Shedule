import subprocess
import sys
import os

# АВТОУСТАНОВКА БИБЛИОТЕК
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

# ======================== ХРАНЕНИЕ ДАННЫХ ========================

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
    default = {"reminder_minutes": 60}
    data = load_json(SETTINGS_FILE, default)
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

# ======================== КНОПКИ ========================

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
    busy_times = [l.get("time") for l in lessons]
    
    buttons = []
    
    for slot in slots:
        if slot in busy_times:
            for idx, lesson in enumerate(lessons):
                if lesson.get("time") == slot:
                    student = lesson.get("student", "Неизвестно")
                    label = f"🗑 {slot} {student}"
                    buttons.append([InlineKeyboardButton(
                        label,
                        callback_data=f"delete_lesson_{key}_{idx}"
                    )])
                    break
        else:
            buttons.append([InlineKeyboardButton(
                f"➕ {slot}",
                callback_data=f"add_slot_{key}_{slot}"
            )])
    
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

def get_slots_edit_keyboard():
    slots = load_slots()
    buttons = []
    for idx, slot in enumerate(slots):
        buttons.append([InlineKeyboardButton(
            f"🕐 {slot}",
            callback_data=f"edit_slot_{idx}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def get_time_picker_keyboard(slot_idx, current_hour):
    buttons = []
    row = []
    for h in range(9, 24):
        label = f"{h:02d}:00"
        if h == current_hour:
            label = f"✅ {label}"
        row.append(InlineKeyboardButton(label, callback_data=f"slot_hour_{slot_idx}_{h}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def get_students_keyboard():
    students = load_students()
    groups = load_groups()
    buttons = []
    
    for student_id, name in students.items():
        buttons.append([InlineKeyboardButton(f"👤 {name}", callback_data=f"student_{student_id}_{name}")])
    
    for group_name, members in groups.items():
        buttons.append([InlineKeyboardButton(f"👥 {group_name} ({len(members)} чел.)", callback_data=f"group_{group_name}")])
    
    buttons.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="manual_add")])
    buttons.append([InlineKeyboardButton("➕ Создать группу", callback_data="create_group")])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    
    return InlineKeyboardMarkup(buttons)

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
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
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

def get_settings_keyboard():
    settings = load_settings()
    current = settings.get("reminder_minutes", 60)
    buttons = [
        [InlineKeyboardButton(f"⏰ Напоминание: {current} мин.", callback_data="settings_show")],
        [InlineKeyboardButton("🕐 Слоты", callback_data="settings_slots")],
        [InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]
    ]
    return InlineKeyboardMarkup(buttons)

# ======================== ФОРМАТИРОВАНИЕ ========================

def format_schedule(day_index, week_offset=0):
    schedule = load_schedule()
    slots = load_slots()
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
        return f"{header}\n\n✨ Нет занятий"
    
    text = f"{header}\n\n"
    for lesson in lessons:
        time = lesson.get("time", "00:00")
        student = lesson.get("student", "Неизвестно")
        zoom = lesson.get("zoom_link", "")
        text += f"🕐 {time} — {student}"
        if zoom:
            text += " 🔗"
        text += "\n"
    
    return text

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
            parse_mode='Markdown'
        )
    elif hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(
            full_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        try:
            await update_or_query.message.reply_text(
                full_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except:
            pass

# ======================== PDF ЭКСПОРТ ========================

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

# ======================== НАПОМИНАНИЯ ========================

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    reminder_minutes = settings.get("reminder_minutes", 60)
    
    schedule = load_schedule()
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    today_key = now.strftime("%Y-%m-%d")
    
    for lesson in schedule.get(today_key, []):
        lesson_time = lesson.get("time", "00:00")
        try:
            h, m = map(int, lesson_time.split(":"))
            lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff = (lesson_dt - now).total_seconds() / 60
            
            if not lesson.get("reminded", False):
                if (reminder_minutes - 5) <= diff <= (reminder_minutes + 5):
                    student = lesson.get("student", "Ученик")
                    topic = lesson.get("topic", "занятие")
                    student_id = lesson.get("student_id")
                    zoom_link = lesson.get("zoom_link", "")
                    
                    if student_id:
                        try:
                            message = f"⏰ Напоминание!\nЧерез {reminder_minutes} мин. занятие:\n👤 {student}\n📚 {topic}\n🕐 {lesson_time}"
                            if zoom_link:
                                message += f"\n🔗 {zoom_link}"
                            await context.bot.send_message(
                                chat_id=int(student_id),
                                text=message
                            )
                            lesson["reminded"] = True
                            save_schedule(schedule)
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
        await update.message.reply_text(f"✅ {first_name}, ты зарегистрирован!")
    else:
        await update.message.reply_text(f"👋 С возвращением, {first_name}!")
    
    commands = [
        BotCommand("schedule", "📅 Расписание на сегодня"),
        BotCommand("week", "📊 Расписание на неделю"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("export", "📄 Экспорт в PDF")
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
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("⚙️ Настройки", reply_markup=keyboard)

# ======================== ОБРАБОТКА КНОПОК ========================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Навигация по дням
    if data == "today":
        today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        day_index = today.weekday()
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = 0
        text = format_schedule(day_index, 0)
        keyboard = get_schedule_keyboard(day_index, 0)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        return
    
    if data.startswith("day_"):
        parts = data.split("_")
        day_index = int(parts[1])
        week_offset = int(parts[2])
        context.user_data['selected_day'] = day_index
        context.user_data['week_offset'] = week_offset
        text = format_schedule(day_index, week_offset)
        keyboard = get_schedule_keyboard(day_index, week_offset)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        return
    
    if data.startswith("week_"):
        week_offset = int(data.split("_")[1])
        context.user_data['week_offset'] = week_offset
        day_index = context.user_data.get('selected_day', 0)
        text = format_schedule(day_index, week_offset)
        keyboard = get_schedule_keyboard(day_index, week_offset)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        return
    
    # Добавление в слот
    if data.startswith("add_slot_"):
        parts = data.split("_")
        key = parts[2]
        slot_time = parts[3]
        
        context.user_data["selected_date"] = datetime.datetime.strptime(key, "%Y-%m-%d").strftime("%d.%m.%Y")
        context.user_data["selected_slot"] = slot_time
        
        students = load_students()
        if not students:
            await query.edit_message_text("❌ Нет учеников. Нажми 'Ввести вручную' и добавь.")
            return
        
        keyboard = get_students_keyboard()
        await query.edit_message_text(
            "👤 *Выбери ученика:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_student"] = True
        return
    
    # Удаление занятия
    if data.startswith("delete_lesson_"):
        parts = data.split("_")
        key = "_".join(parts[2:-1])
        idx = int(parts[-1])
        schedule = load_schedule()
        if key in schedule and 0 <= idx < len(schedule[key]):
            del schedule[key][idx]
            if not schedule[key]:
                del schedule[key]
            save_schedule(schedule)
            await query.edit_message_text("✅ Удалено!")
            await show_schedule(query, context)
        else:
            await query.edit_message_text("❌ Не найдено")
        return
    
    # Выбор ученика из списка
    if data.startswith("student_"):
        parts = data.split("_")
        student_id = parts[1]
        student_name = "_".join(parts[2:])
        
        slot_time = context.user_data.get("selected_slot")
        selected_date = context.user_data.get("selected_date")
        
        if slot_time and selected_date:
            # Добавляем ученика в слот
            day, month, year = map(int, selected_date.split('.'))
            key = f"{year:04d}-{month:02d}-{day:02d}"
            schedule = load_schedule()
            if key not in schedule:
                schedule[key] = []
            schedule[key].append({
                "time": slot_time,
                "student": student_name,
                "student_id": student_id,
                "topic": "-",
                "reminded": False,
                "zoom_link": ""
            })
            save_schedule(schedule)
            context.user_data.pop("selected_slot", None)
            context.user_data.pop("selected_date", None)
            
            # Спрашиваем про повтор
            buttons = [
                [InlineKeyboardButton("❌ Только этот день", callback_data=f"repeat_after_no_{key}_{slot_time}")],
                [InlineKeyboardButton("📅 На месяц", callback_data=f"repeat_after_month_{key}_{slot_time}")],
                [InlineKeyboardButton("📅 До 31 мая", callback_data=f"repeat_after_year_{key}_{slot_time}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
            ]
            await query.edit_message_text(
                f"✅ {student_name} на {slot_time}!\n\nПовторить занятие?",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown'
            )
            return
        
        context.user_data["selected_student"] = {"id": student_id, "name": student_name}
        await query.edit_message_text(
            f"👤 {student_name}\n\n📅 Выбери дату:",
            reply_markup=get_date_keyboard(0),
            parse_mode='Markdown'
        )
        context.user_data.pop("waiting_for_student", None)
        return
    
    # Повтор после добавления в слот
    if data.startswith("repeat_after_"):
        parts = data.split("_")
        repeat_type = parts[2]  # no, month, year
        key = parts[3]
        slot_time = parts[4]
        
        schedule = load_schedule()
        
        if repeat_type == "no":
            await query.edit_message_text("✅ Занятие добавлено!")
            await show_schedule(query, context)
            context.user_data.clear()
            return
        
        # Находим ученика на этом слоте
        found = False
        if key in schedule:
            for lesson in schedule[key]:
                if lesson.get("time") == slot_time:
                    student_name = lesson.get("student")
                    student_id = lesson.get("student_id")
                    found = True
                    
                    day, month, year = map(int, key.split('-'))
                    start_date = datetime.datetime(year, month, day)
                    
                    if repeat_type == "month":
                        end_date = start_date + datetime.timedelta(days=28)
                        current = start_date + datetime.timedelta(days=7)
                        count = 1
                        while current <= end_date:
                            new_key = current.strftime("%Y-%m-%d")
                            if new_key not in schedule:
                                schedule[new_key] = []
                            schedule[new_key].append({
                                "time": slot_time,
                                "student": student_name,
                                "student_id": student_id,
                                "topic": "-",
                                "reminded": False,
                                "zoom_link": ""
                            })
                            count += 1
                            current += datetime.timedelta(days=7)
                        save_schedule(schedule)
                        await query.edit_message_text(f"✅ Добавлено {count} занятий (на месяц)!")
                        await show_schedule(query, context)
                        context.user_data.clear()
                        return
                    
                    if repeat_type == "year":
                        end_date = datetime.datetime(year, 5, 31)
                        if start_date > end_date:
                            await query.edit_message_text("❌ Дата позже 31 мая")
                            context.user_data.clear()
                            return
                        current = start_date + datetime.timedelta(days=7)
                        count = 1
                        while current <= end_date:
                            new_key = current.strftime("%Y-%m-%d")
                            if new_key not in schedule:
                                schedule[new_key] = []
                            schedule[new_key].append({
                                "time": slot_time,
                                "student": student_name,
                                "student_id": student_id,
                                "topic": "-",
                                "reminded": False,
                                "zoom_link": ""
                            })
                            count += 1
                            current += datetime.timedelta(days=7)
                        save_schedule(schedule)
                        await query.edit_message_text(f"✅ Добавлено {count} занятий (до 31 мая)!")
                        await show_schedule(query, context)
                        context.user_data.clear()
                        return
        
        if not found:
            await query.edit_message_text("❌ Ошибка: занятие не найдено")
            context.user_data.clear()
        return
    
    # Дата
    if data.startswith("date_"):
        date_str = data.replace("date_", "")
        context.user_data["selected_date"] = date_str
        await query.edit_message_text(
            "🕐 *Выбери час:*",
            reply_markup=get_time_hours_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    if data.startswith("month_"):
        if data == "month_today":
            month_offset = 0
        else:
            month_offset = int(data.split("_")[1])
        context.user_data["month_offset"] = month_offset
        student_name = context.user_data.get("selected_student", {}).get("name", "Ученик")
        await query.edit_message_text(
            f"👤 {student_name}\n\n📅 Выбери дату:",
            reply_markup=get_date_keyboard(month_offset),
            parse_mode='Markdown'
        )
        return
    
    # Часы
    if data.startswith("hour_"):
        hour = int(data.split("_")[1])
        context.user_data["selected_hour"] = hour
        await query.edit_message_text(
            "🕐 *Выбери минуты:*",
            reply_markup=get_time_minutes_keyboard(hour),
            parse_mode='Markdown'
        )
        return
    
    # Минуты
    if data.startswith("min_"):
        parts = data.split("_")
        hour = int(parts[1])
        minute = parts[2]
        time_str = f"{hour:02d}:{minute}"
        context.user_data["selected_time"] = time_str
        
        student = context.user_data.get("selected_student", {}).get("name", "Ученик")
        date_str = context.user_data.get("selected_date", "Дата")
        
        buttons = [
            [InlineKeyboardButton("❌ Только этот день", callback_data="repeat_no")],
            [InlineKeyboardButton("📅 На месяц", callback_data="repeat_month")],
            [InlineKeyboardButton("📅 До 31 мая", callback_data="repeat_year")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
        ]
        await query.edit_message_text(
            f"👤 {student}\n📅 {date_str}\n🕐 {time_str}\n\nПовторить?",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='Markdown'
        )
        return
    
    # Повтор (старый вариант)
    if data.startswith("repeat_"):
        student_data = context.user_data.get("selected_student")
        date_str = context.user_data.get("selected_date")
        time_str = context.user_data.get("selected_time")
        
        if not student_data or not date_str or not time_str:
            await query.edit_message_text("❌ Ошибка")
            context.user_data.clear()
            return
        
        day, month, year = map(int, date_str.split('.'))
        start_date = datetime.datetime(year, month, day)
        schedule = load_schedule()
        
        def add_lesson(key):
            if key not in schedule:
                schedule[key] = []
            schedule[key].append({
                "time": time_str,
                "student": student_data["name"],
                "student_id": student_data["id"],
                "topic": "-",
                "reminded": False,
                "zoom_link": ""
            })
        
        if data == "repeat_no":
            add_lesson(start_date.strftime("%Y-%m-%d"))
            save_schedule(schedule)
            await query.edit_message_text("✅ Добавлено!")
            await show_schedule(query, context)
            context.user_data.clear()
            return
        
        if data == "repeat_month":
            end_date = start_date + datetime.timedelta(days=28)
            current = start_date
            count = 0
            while current <= end_date:
                add_lesson(current.strftime("%Y-%m-%d"))
                count += 1
                current += datetime.timedelta(days=7)
            save_schedule(schedule)
            await query.edit_message_text(f"✅ Добавлено {count} занятий!")
            await show_schedule(query, context)
            context.user_data.clear()
            return
        
        if data == "repeat_year":
            end_date = datetime.datetime(year, 5, 31)
            if start_date > end_date:
                await query.edit_message_text("❌ Дата позже 31 мая")
                context.user_data.clear()
                return
            current = start_date
            count = 0
            while current <= end_date:
                add_lesson(current.strftime("%Y-%m-%d"))
                count += 1
                current += datetime.timedelta(days=7)
            save_schedule(schedule)
            await query.edit_message_text(f"✅ Добавлено {count} занятий!")
            await show_schedule(query, context)
            context.user_data.clear()
            return
    
    # Отмена
    if data == "cancel_add":
        await query.edit_message_text("❌ Отменено")
        context.user_data.clear()
        await show_schedule(query, context)
        return
    
    # Настройки
    if data == "settings":
        await settings_menu(update, context)
        return
    
    if data == "settings_back":
        await show_schedule(query, context)
        return
    
    if data == "settings_show":
        settings = load_settings()
        current = settings.get("reminder_minutes", 60)
        await query.edit_message_text(
            f"⏰ Напоминание: {current} мин.",
            reply_markup=get_settings_keyboard()
        )
        return
    
    if data == "settings_slots":
        keyboard = get_slots_edit_keyboard()
        await query.edit_message_text(
            "🕐 *Редактирование слотов*\n\n"
            "Нажми на слот, чтобы изменить его время.\n"
            "Всего слотов: 9\n\n"
            "⚠️ Если изменишь время слота, занятия, "
            "привязанные к старому времени, НЕ перенесутся "
            "автоматически! Их нужно будет перенести вручную.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return
    
    # Редактирование слота
    if data.startswith("edit_slot_"):
        slot_idx = int(data.split("_")[2])
        slots = load_slots()
        if slot_idx < len(slots):
            current_time = slots[slot_idx]
            hour = int(current_time.split(":")[0])
            keyboard = get_time_picker_keyboard(slot_idx, hour)
            await query.edit_message_text(
                f"🕐 *Выбери новое время для слота #{slot_idx + 1}*\n"
                f"Текущее: {current_time}",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        return
    
    if data.startswith("slot_hour_"):
        parts = data.split("_")
        slot_idx = int(parts[2])
        new_hour = int(parts[3])
        
        slots = load_slots()
        if slot_idx < len(slots):
            new_time = f"{new_hour:02d}:00"
            
            if new_time in slots and slots.index(new_time) != slot_idx:
                await query.edit_message_text(
                    f"❌ Время {new_time} уже занято другим слотом!\n"
                    f"Выбери другое время.",
                    reply_markup=get_time_picker_keyboard(slot_idx, int(slots[slot_idx].split(":")[0])),
                    parse_mode='Markdown'
                )
                return
            
            old_time = slots[slot_idx]
            slots[slot_idx] = new_time
            save_slots(slots)
            
            await query.edit_message_text(
                f"✅ Время слота #{slot_idx + 1} изменено:\n"
                f"{old_time} → {new_time}\n\n"
                "⚠️ Проверь расписание — занятия на старом времени остались, "
                "их нужно перенести вручную!",
                parse_mode='Markdown'
            )
            keyboard = get_slots_edit_keyboard()
            await query.edit_message_text(
                "🕐 *Редактирование слотов*\n\n"
                "Нажми на слот, чтобы изменить его время.",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        return
    
    # Ручной ввод
    if data == "manual_add":
        await query.edit_message_text("✏️ Введи имя ученика:")
        context.user_data["waiting_for_manual"] = True
        return
    
    if data == "create_group":
        await query.edit_message_text("👥 Создание группы\n\nВведи название:")
        context.user_data["waiting_for_group_name"] = True
        return
    
    if data == "empty" or data == "weekday" or data == "month_title":
        return

# ======================== ОБРАБОТЧИКИ ТЕКСТА ========================

async def handle_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_manual"):
        return
    
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
    
    slot_time = context.user_data.get("selected_slot")
    selected_date = context.user_data.get("selected_date")
    
    if slot_time and selected_date:
        day, month, year = map(int, selected_date.split('.'))
        key = f"{year:04d}-{month:02d}-{day:02d}"
        schedule = load_schedule()
        if key not in schedule:
            schedule[key] = []
        schedule[key].append({
            "time": slot_time,
            "student": name,
            "student_id": user_id,
            "topic": "-",
            "reminded": False,
            "zoom_link": ""
        })
        save_schedule(schedule)
        context.user_data.pop("selected_slot", None)
        context.user_data.pop("selected_date", None)
        await update.message.reply_text(f"✅ {name} добавлен на {slot_time}!")
        await show_schedule(update, context)
    else:
        keyboard = get_students_keyboard()
        await update.message.reply_text(
            "👤 *Теперь выбери ученика для слота:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_student"] = True

async def handle_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_group_name"):
        return
    group_name = update.message.text.strip()
    groups = load_groups()
    if group_name in groups:
        await update.message.reply_text(f"❌ Группа {group_name} уже есть")
        context.user_data.pop("waiting_for_group_name", None)
        return
    groups[group_name] = []
    save_groups(groups)
    await update.message.reply_text(f"✅ Группа {group_name} создана!\nВведи имена через запятую:")
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
    await update.message.reply_text(f"✅ Добавлены: {', '.join(names)}")
    await show_schedule(update, context)
    context.user_data.pop("waiting_for_group_members", None)

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_members))
    
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
