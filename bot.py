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

# ======================== КНОПКИ ========================

def get_schedule_with_empty_slots(day_index, week_offset=0):
    """Расписание с пустыми слотами (➕) и учениками (🗑)"""
    schedule = load_schedule()
    days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    day_name = days[day_index]
    
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    start_of_week = today - datetime.timedelta(days=today.weekday())
    target_date = start_of_week + datetime.timedelta(days=day_index + week_offset * 7)
    key = target_date.strftime("%Y-%m-%d")
    
    lessons = schedule.get(key, [])
    lessons.sort(key=lambda x: x.get("time", "00:00"))
    
    all_slots = ["10:00", "11:00", "12:00", "13:00", "14:00", 
                 "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"]
    busy_times = [l.get("time") for l in lessons]
    
    buttons = []
    
    for slot in all_slots:
        if slot in busy_times:
            for idx, lesson in enumerate(lessons):
                if lesson.get("time") == slot:
                    student = lesson.get("student", "Неизвестно")
                    topic = lesson.get("topic", "-")
                    zoom = lesson.get("zoom_link", "")
                    label = f"🕐 {slot} — {student}"
                    if zoom:
                        label += " 🔗"
                    if topic != "-":
                        label += f" ({topic})"
                    buttons.append([InlineKeyboardButton(
                        f"🗑 {label}",
                        callback_data=f"delete_lesson_{key}_{idx}"
                    )])
                    break
        else:
            buttons.append([InlineKeyboardButton(
                f"➕ {slot} свободно",
                callback_data=f"add_slot_{key}_{slot}"
            )])
    
    if not buttons:
        buttons.append([InlineKeyboardButton("✨ Весь день занят", callback_data="empty")])
    
    nav_buttons = [
        InlineKeyboardButton("◀ Назад", callback_data=f"week_{week_offset-1}"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
        InlineKeyboardButton("Вперёд ▶", callback_data=f"week_{week_offset+1}")
    ]
    
    action_buttons = [
        InlineKeyboardButton("➕ Добавить", callback_data="add_lesson"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    ]
    
    keyboard = buttons + [nav_buttons] + [action_buttons]
    return InlineKeyboardMarkup(keyboard)

def get_day_keyboard(week_offset=0, selected_day=0):
    return get_schedule_with_empty_slots(selected_day, week_offset)

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
    """Календарь на месяц с возможностью листать"""
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
        [InlineKeyboardButton("➖ 5 мин", callback_data="set_dec"), 
         InlineKeyboardButton("➕ 5 мин", callback_data="set_inc")],
        [InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]
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
        zoom_link = lesson.get("zoom_link", "")
        text += f"🕐 *{time}* — {student}"
        if zoom_link:
            text += f" 🔗"
        text += "\n"
        if topic != "-":
            text += f"   📚 {topic}\n"
        text += "\n"
    
    return text

async def show_schedule_message(update_or_query, context, text_prefix=""):
    """Универсальная функция для показа расписания"""
    today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    day_index = today.weekday()
    context.user_data['selected_day'] = day_index
    context.user_data['week_offset'] = 0
    
    text = format_schedule(day_index, 0)
    keyboard = get_day_keyboard(0, day_index)
    
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
            print("Не удалось отправить сообщение")

# ======================== PDF ЭКСПОРТ ========================

def generate_week_pdf():
    schedule = load_schedule()
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
        await update.message.reply_text(f"✅ {first_name}, ты зарегистрирован как ученик!")
    else:
        await update.message.reply_text(f"👋 С возвращением, {first_name}!")
    
    commands = [
        BotCommand("schedule", "📅 Расписание на сегодня"),
        BotCommand("week", "📊 Расписание на неделю"),
        BotCommand("add", "➕ Добавить занятие"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("export", "📄 Экспорт в PDF")
    ]
    await context.bot.set_my_commands(commands)
    
    await show_schedule_message(update, context)

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_schedule_message(update, context)

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
    await update.message.reply_text("📄 Генерирую PDF с расписанием на неделю...")
    
    try:
        pdf_buffer = generate_week_pdf()
        
        today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        filename = f"расписание_{today.strftime('%d.%m')}.pdf"
        
        await update.message.reply_document(
            document=pdf_buffer,
            filename=filename,
            caption="📅 Расписание на неделю"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при генерации PDF: {e}")

async def add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    students = load_students()
    groups = load_groups()
    
    if not students and not groups:
        msg = "❌ Нет зарегистрированных учеников и групп.\n\n"
        msg += "✏️ Введи имя ученика вручную командой:\n`/add_manual Имя`\n\n"
        msg += "👥 Или создай группу: /create_group"
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    keyboard = get_students_keyboard()
    text = "👤 *Выбери ученика или группу:*"
    
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

async def add_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            await update.message.reply_text(
                "✏️ Напиши:\n`/add_manual Имя`\n\n"
                "Пример: `/add_manual Иванов`",
                parse_mode='Markdown'
            )
            return
        
        student_name = " ".join(args)
        user_id = f"manual_{datetime.datetime.now().timestamp()}"
        
        students = load_students()
        students[user_id] = student_name
        save_students(students)
        
        await update.message.reply_text(f"✅ Ученик *{student_name}* добавлен!\nТеперь его можно выбрать из списка.", parse_mode='Markdown')
        await show_schedule_message(update, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "👥 *Создание группы*\n\n"
            "Введи название группы:\n"
            "Например: `Математика 10А`",
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_group_name"] = True
    else:
        await update.message.reply_text(
            "👥 *Создание группы*\n\n"
            "Введи название группы:\n"
            "Например: `Математика 10А`",
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_group_name"] = True

async def handle_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_group_name"):
        return
    
    group_name = update.message.text.strip()
    groups = load_groups()
    
    if group_name in groups:
        await update.message.reply_text(f"❌ Группа *{group_name}* уже существует!", parse_mode='Markdown')
        context.user_data.pop("waiting_for_group_name", None)
        return
    
    groups[group_name] = []
    save_groups(groups)
    
    await update.message.reply_text(
        f"✅ Группа *{group_name}* создана!\n\n"
        "Теперь добавь учеников в группу.\n"
        "Введи имена учеников через запятую:\n"
        "`Иванов, Петров, Сидорова`",
        parse_mode='Markdown'
    )
    context.user_data["waiting_for_group_members"] = group_name

async def handle_group_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_name = context.user_data.get("waiting_for_group_members")
    if not group_name:
        return
    
    names = [name.strip() for name in update.message.text.split(',')]
    groups = load_groups()
    students = load_students()
    
    added = []
    for name in names:
        if name not in groups[group_name]:
            groups[group_name].append(name)
            added.append(name)
        
        exists = False
        for sid, sname in students.items():
            if sname == name:
                exists = True
                break
        if not exists:
            students[f"manual_{datetime.datetime.now().timestamp()}"] = name
    
    save_groups(groups)
    save_students(students)
    
    await update.message.reply_text(
        f"✅ В группу *{group_name}* добавлены:\n{', '.join(added)}",
        parse_mode='Markdown'
    )
    await show_schedule_message(update, context)
    context.user_data.pop("waiting_for_group_members", None)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_settings_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "⚙️ *Настройки*\n\n"
            "Выбери время напоминания:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "⚙️ *Настройки*\n\n"
            "Выбери время напоминания:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

async def select_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        await show_schedule_message(query, context)
        return
    
    if data == "manual_add":
        await query.edit_message_text(
            "✏️ Введи имя ученика вручную командой:\n"
            "`/add_manual Имя`\n\n"
            "Пример: `/add_manual Иванов`",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return
    
    if data == "create_group":
        await create_group(update, context)
        return
    
    if data.startswith("group_"):
        group_name = data.replace("group_", "")
        context.user_data["selected_group"] = group_name
        context.user_data["month_offset"] = 0
        
        await query.edit_message_text(
            f"👥 Группа: *{group_name}*\n\n"
            "📅 *Выбери дату:*",
            reply_markup=get_date_keyboard(0),
            parse_mode='Markdown'
        )
        return
    
    if data.startswith("student_"):
        parts = data.split("_")
        student_id = parts[1]
        student_name = "_".join(parts[2:])
        
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
                "student": student_name,
                "student_id": student_id,
                "topic": "-",
                "group": None,
                "reminded": False,
                "zoom_link": ""
            })
            save_schedule(schedule)
            
            context.user_data.pop("selected_slot", None)
            context.user_data.pop("selected_date", None)
            
            await query.edit_message_text(f"✅ Ученик *{student_name}* добавлен на {slot_time}!")
            await show_schedule_message(query, context)
            return
        
        context.user_data["selected_student"] = {
            "id": student_id,
            "name": student_name
        }
        context.user_data["month_offset"] = 0
        
        await query.edit_message_text(
            f"👤 Ученик: *{student_name}*\n\n"
            "📅 *Выбери дату:*",
            reply_markup=get_date_keyboard(0),
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
        await show_schedule_message(query, context)
        return
    
    if data.startswith("month_"):
        if data == "month_today":
            month_offset = 0
        else:
            month_offset = int(data.split("_")[1])
        context.user_data["month_offset"] = month_offset
        
        student_name = context.user_data.get("selected_student", {}).get("name", context.user_data.get("selected_group", "Ученик"))
        
        await query.edit_message_text(
            f"👤 Ученик/группа: *{student_name}*\n\n"
            "📅 *Выбери дату:*",
            reply_markup=get_date_keyboard(month_offset),
            parse_mode='Markdown'
        )
        return
    
    if data == "empty" or data == "weekday" or data == "month_title":
        return
    
    if data.startswith("date_"):
        date_str = data.replace("date_", "")
        context.user_data["selected_date"] = date_str
        
        student_name = context.user_data.get("selected_student", {}).get("name", context.user_data.get("selected_group", "Ученик"))
        
        await query.edit_message_text(
            f"👤 Ученик/группа: *{student_name}*\n"
            f"📅 Дата: *{date_str}*\n\n"
            "🕐 *Выбери час:*",
            reply_markup=get_time_hours_keyboard(),
            parse_mode='Markdown'
        )
        return

async def select_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        await show_schedule_message(query, context)
        return
    
    if data.startswith("hour_"):
        hour = int(data.split("_")[1])
        context.user_data["selected_hour"] = hour
        
        student_name = context.user_data.get("selected_student", {}).get("name", context.user_data.get("selected_group", "Ученик"))
        date_str = context.user_data.get("selected_date", "Дата")
        
        await query.edit_message_text(
            f"👤 Ученик/группа: *{student_name}*\n"
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
        await show_schedule_message(query, context)
        return
    
    if data.startswith("min_"):
        parts = data.split("_")
        hour = int(parts[1])
        minute = parts[2]
        time_str = f"{hour:02d}:{minute}"
        
        context.user_data["selected_time"] = time_str
        student_name = context.user_data.get("selected_student", {}).get("name", context.user_data.get("selected_group", "Ученик"))
        date_str = context.user_data.get("selected_date", "Дата")
        
        buttons = [
            [InlineKeyboardButton("📎 Добавить ссылку", callback_data="add_zoom")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_zoom")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_text(
            f"👤 Ученик/группа: *{student_name}*\n"
            f"📅 Дата: *{date_str}*\n"
            f"🕐 Время: *{time_str}*\n\n"
            "🔗 *Добавить ссылку на Zoom/Meet?*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

async def select_zoom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        await show_schedule_message(query, context)
        return
    
    if data == "skip_zoom":
        context.user_data["zoom_link"] = ""
        await show_repeat_choice(update, context, query)
        return
    
    if data == "add_zoom":
        await query.edit_message_text(
            "🔗 *Вставь ссылку на Zoom/Meet:*\n\n"
            "Например: `https://zoom.us/j/123456789`",
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_zoom"] = True
        return

async def handle_zoom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_zoom"):
        return
    
    zoom_link = update.message.text.strip()
    context.user_data["zoom_link"] = zoom_link
    context.user_data["waiting_for_zoom"] = False
    
    await update.message.reply_text("✅ Ссылка сохранена!")
    await show_repeat_choice(update, context, None)

async def show_repeat_choice(update, context, query=None):
    student_name = context.user_data.get("selected_student", {}).get("name", context.user_data.get("selected_group", "Ученик"))
    date_str = context.user_data.get("selected_date", "Дата")
    time_str = context.user_data.get("selected_time", "00:00")
    
    buttons = [
        [InlineKeyboardButton("❌ Только этот день", callback_data="repeat_no")],
        [InlineKeyboardButton("📅 На месяц (4 недели)", callback_data="repeat_month")],
        [InlineKeyboardButton("📅 До конца учебного года", callback_data="repeat_year")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = (
        f"👤 Ученик/группа: *{student_name}*\n"
        f"📅 Дата: *{date_str}*\n"
        f"🕐 Время: *{time_str}*\n\n"
        "📋 *Повторить занятие?*"
    )
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

async def select_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_add":
        await query.edit_message_text("❌ Добавление отменено")
        context.user_data.clear()
        await show_schedule_message(query, context)
        return
    
    student_data = context.user_data.get("selected_student")
    group_name = context.user_data.get("selected_group")
    date_str = context.user_data.get("selected_date")
    time_str = context.user_data.get("selected_time")
    zoom_link = context.user_data.get("zoom_link", "")
    
    if not date_str or not time_str:
        await query.edit_message_text("❌ Ошибка: данные потеряны")
        context.user_data.clear()
        await show_schedule_message(query, context)
        return
    
    schedule = load_schedule()
    
    def add_lesson_to_date(key):
        if key not in schedule:
            schedule[key] = []
        
        if group_name:
            groups = load_groups()
            for name in groups.get(group_name, []):
                students = load_students()
                for sid, sname in students.items():
                    if sname == name:
                        schedule[key].append({
                            "time": time_str,
                            "student": name,
                            "student_id": sid,
                            "topic": "-",
                            "group": group_name,
                            "reminded": False,
                            "zoom_link": zoom_link
                        })
                        break
        elif student_data:
            schedule[key].append({
                "time": time_str,
                "student": student_data["name"],
                "student_id": student_data["id"],
                "topic": "-",
                "group": None,
                "reminded": False,
                "zoom_link": zoom_link
            })
    
    day, month, year = map(int, date_str.split('.'))
    start_date = datetime.datetime(year, month, day)
    
    if data == "repeat_no":
        key = start_date.strftime("%Y-%m-%d")
        add_lesson_to_date(key)
        save_schedule(schedule)
        await show_schedule_message(query, context, "✅ *Занятие добавлено!*")
        context.user_data.clear()
        return
    
    if data == "repeat_month":
        end_date = start_date + datetime.timedelta(days=28)
        current_date = start_date
        added_count = 0
        while current_date <= end_date:
            key = current_date.strftime("%Y-%m-%d")
            add_lesson_to_date(key)
            added_count += 1
            current_date += datetime.timedelta(days=7)
        save_schedule(schedule)
        await show_schedule_message(query, context, f"✅ *Занятия добавлены! ({added_count} занятий)*")
        context.user_data.clear()
        return
    
    if data == "repeat_year":
        end_date = datetime.datetime(year, 5, 31)
        if start_date > end_date:
            await query.edit_message_text("❌ Дата позже конца учебного года (31 мая)")
            context.user_data.clear()
            await show_schedule_message(query, context)
            return
        current_date = start_date
        added_count = 0
        while current_date <= end_date:
            key = current_date.strftime("%Y-%m-%d")
            add_lesson_to_date(key)
            added_count += 1
            current_date += datetime.timedelta(days=7)
        save_schedule(schedule)
        await show_schedule_message(query, context, f"✅ *Занятия добавлены! ({added_count} занятий)*")
        context.user_data.clear()
        return

async def delete_lesson_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "back_to_schedule":
        await show_schedule_message(query, context)
        return
    
    if data.startswith("delete_lesson_"):
        parts = data.split("_")
        key = "_".join(parts[2:-1])
        idx = int(parts[-1])
        
        schedule = load_schedule()
        if key in schedule and 0 <= idx < len(schedule[key]):
            lesson = schedule[key][idx]
            student = lesson.get("student", "Неизвестно")
            time = lesson.get("time", "00:00")
            
            del schedule[key][idx]
            if not schedule[key]:
                del schedule[key]
            save_schedule(schedule)
            
            await query.edit_message_text(
                f"✅ *Удалено занятие:* {time} — {student}",
                parse_mode='Markdown'
            )
            await show_schedule_message(query, context)
        else:
            await query.edit_message_text("❌ Занятие не найдено")
        return
    
    if data.startswith("add_slot_"):
        parts = data.split("_")
        key = parts[2]
        slot_time = parts[3]
        
        context.user_data["selected_date"] = datetime.datetime.strptime(key, "%Y-%m-%d").strftime("%d.%m.%Y")
        context.user_data["selected_slot"] = slot_time
        
        students = load_students()
        if not students:
            await query.edit_message_text("❌ Нет зарегистрированных учеников. Сначала добавь учеников через /add_manual")
            return
        
        keyboard = get_students_keyboard()
        await query.edit_message_text(
            "👤 *Выбери ученика для этого слота:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        context.user_data["waiting_for_student"] = True
        return

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    settings = load_settings()
    
    if data == "settings":
        await settings_menu(update, context)
        return
    
    if data == "settings_back":
        await show_schedule_message(query, context)
        return
    
    if data == "settings_show":
        current = settings.get("reminder_minutes", 60)
        await query.edit_message_text(
            f"⏰ *Текущее время напоминания:* {current} минут\n\n"
            "Изменить можно кнопками ниже:",
            reply_markup=get_settings_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    if data == "set_inc":
        current = settings.get("reminder_minutes", 60)
        new_value = min(current + 5, 1440)
        settings["reminder_minutes"] = new_value
        save_settings(settings)
        await show_schedule_message(query, context, f"⏰ *Напоминание: {new_value} мин.*")
        return
    
    if data == "set_dec":
        current = settings.get("reminder_minutes", 60)
        new_value = max(current - 5, 5)
        settings["reminder_minutes"] = new_value
        save_settings(settings)
        await show_schedule_message(query, context, f"⏰ *Напоминание: {new_value} мин.*")
        return

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
    
    if data == "settings":
        await settings_callback(update, context)
        return
    
    if data.startswith("settings") or data.startswith("set_"):
        await settings_callback(update, context)
        return
    
    if data.startswith("delete_lesson_") or data.startswith("add_slot_") or data == "back_to_schedule":
        await delete_lesson_confirm(update, context)
        return
    
    if data.startswith("student_") or data == "cancel_add" or data == "manual_add" or data == "create_group" or data.startswith("group_"):
        await select_student(update, context)
        return
    
    if data.startswith("date_") or data == "cancel_add" or data.startswith("month_") or data == "month_today" or data == "empty" or data == "weekday" or data == "month_title":
        await select_date(update, context)
        return
    
    if data.startswith("hour_") or data == "cancel_add":
        await select_hour(update, context)
        return
    
    if data.startswith("min_") or data == "cancel_add" or data == "add_zoom" or data == "skip_zoom":
        await select_minutes(update, context)
        return
    
    if data.startswith("repeat_"):
        await select_repeat(update, context)
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
    app.add_handler(CommandHandler("add_manual", add_manual))
    app.add_handler(CommandHandler("create_group", create_group))
    app.add_handler(CommandHandler("settings", settings_menu))
    app.add_handler(CommandHandler("export", export_week))

    app.add_handler(CallbackQueryHandler(handle_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_members))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_zoom_input))

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
