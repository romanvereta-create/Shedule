# Добавьте эти изменения в web_app_data_handler

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от Mini App"""
    try:
        data = json.loads(update.message.web_app_data.data)
    except:
        return
    
    action = data.get('action')
    user_id = data.get('user_id')
    
    async def send_response(response_data):
        response_json = json.dumps(response_data, ensure_ascii=False)
        await update.message.reply_text(f"__MINIAPP_RESPONSE__{response_json}")
    
    # ========== ПОЛУЧИТЬ РАСПИСАНИЕ ==========
    if action == 'get_schedule':
        date = data.get('date')  # Получаем конкретную дату
        
        if not date:
            # Если дата не передана, используем сегодня
            today = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
            date = today.strftime("%Y-%m-%d")
        
        slots = load_slots()
        schedule = load_schedule()
        lessons = schedule.get(date, [])
        
        # Сортируем занятия по времени
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        response = {
            "action": "get_schedule",
            "slots": slots,
            "lessons": lessons,
            "date": date
        }
        await send_response(response)
        return
    
    # ========== ПОЛУЧИТЬ УЧЕНИКОВ ==========
    if action == 'get_students':
        students = load_students()
        response = {
            "action": "get_students",
            "students": students
        }
        await send_response(response)
        return
    
    # ========== ПОЛУЧИТЬ СЛОТЫ ==========
    if action == 'get_slots':
        slots = load_slots()
        response = {
            "action": "get_slots",
            "slots": slots
        }
        await send_response(response)
        return
    
    # ========== ДОБАВИТЬ ЗАНЯТИЕ ==========
    if action == 'add_lesson':
        date = data.get('date')
        time = data.get('time')
        student = data.get('student')
        student_id = data.get('student_id')
        repeat = data.get('repeat', 'no')
        reminder = data.get('reminder', 60)
        zoom = data.get('zoom', '')
        
        if not date or not time or not student:
            response = {"action": "add_lesson", "status": "error", "message": "Не все поля заполнены"}
            await send_response(response)
            return
        
        schedule = load_schedule()
        if date not in schedule:
            schedule[date] = []
        
        # Проверяем, не занят ли слот
        for lesson in schedule[date]:
            if lesson.get('time') == time:
                response = {"action": "add_lesson", "status": "error", "message": f"Слот {time} уже занят!"}
                await send_response(response)
                return
        
        # Добавляем занятие
        schedule[date].append({
            "time": time,
            "student": student,
            "student_id": student_id,
            "topic": "-",
            "reminded": False,
            "zoom_link": zoom,
            "reminder_minutes": reminder
        })
        save_schedule(schedule)
        
        # Если повтор — добавляем на другие даты
        if repeat == "month":
            year, month, day = map(int, date.split('-'))
            start_date = datetime.datetime(year, month, day)
            end_date = start_date + datetime.timedelta(days=28)
            current = start_date + datetime.timedelta(days=7)
            while current <= end_date:
                new_key = current.strftime("%Y-%m-%d")
                if new_key not in schedule:
                    schedule[new_key] = []
                schedule[new_key].append({
                    "time": time,
                    "student": student,
                    "student_id": student_id,
                    "topic": "-",
                    "reminded": False,
                    "zoom_link": zoom,
                    "reminder_minutes": reminder
                })
                current += datetime.timedelta(days=7)
            save_schedule(schedule)
        elif repeat == "year":
            year, month, day = map(int, date.split('-'))
            start_date = datetime.datetime(year, month, day)
            end_date = datetime.datetime(year, 5, 31)
            if start_date > end_date:
                end_date = datetime.datetime(year + 1, 5, 31)
            current = start_date + datetime.timedelta(days=7)
            while current <= end_date:
                new_key = current.strftime("%Y-%m-%d")
                if new_key not in schedule:
                    schedule[new_key] = []
                schedule[new_key].append({
                    "time": time,
                    "student": student,
                    "student_id": student_id,
                    "topic": "-",
                    "reminded": False,
                    "zoom_link": zoom,
                    "reminder_minutes": reminder
                })
                current += datetime.timedelta(days=7)
            save_schedule(schedule)
        
        # Возвращаем обновленное расписание для этой даты
        updated_lessons = schedule.get(date, [])
        updated_lessons.sort(key=lambda x: x.get("time", "00:00"))
        slots = load_slots()
        
        response = {
            "action": "add_lesson",
            "status": "ok",
            "lessons": updated_lessons,
            "slots": slots,
            "date": date
        }
        await send_response(response)
        return
    
    # ========== УДАЛИТЬ ЗАНЯТИЕ ==========
    if action == 'delete_lesson':
        date = data.get('date')
        time = data.get('time')
        
        if not date or not time:
            response = {"action": "delete_lesson", "status": "error", "message": "Не указана дата или время"}
            await send_response(response)
            return
        
        schedule = load_schedule()
        if date in schedule:
            schedule[date] = [l for l in schedule[date] if l.get('time') != time]
            if not schedule[date]:
                del schedule[date]
            save_schedule(schedule)
        
        slots = load_slots()
        lessons = schedule.get(date, [])
        lessons.sort(key=lambda x: x.get("time", "00:00"))
        
        response = {
            "action": "delete_lesson",
            "status": "ok",
            "lessons": lessons,
            "slots": slots,
            "date": date
        }
        await send_response(response)
        return
    
    # ========== ИЗМЕНИТЬ ВРЕМЯ ==========
    if action == 'edit_time':
        old_time = data.get('old_time')
        new_time = data.get('new_time')
        
        slots = load_slots()
        if old_time in slots:
            idx = slots.index(old_time)
            slots[idx] = new_time
            slots = sorted(slots)
            save_slots(slots)
        
        response = {"action": "edit_time", "status": "ok", "slots": slots}
        await send_response(response)
        return
    
    # ========== НАСТРОИТЬ НАПОМИНАНИЕ ==========
    if action == 'set_reminder':
        date = data.get('date')
        time = data.get('time')
        minutes = data.get('minutes')
        
        if not date or not time:
            response = {"action": "set_reminder", "status": "error", "message": "Не указана дата или время"}
            await send_response(response)
            return
        
        schedule = load_schedule()
        if date in schedule:
            for lesson in schedule[date]:
                if lesson.get('time') == time:
                    lesson['reminder_minutes'] = minutes
                    break
            save_schedule(schedule)
        
        response = {"action": "set_reminder", "status": "ok"}
        await send_response(response)
        return
    
    # ========== НАСТРОЙКИ ==========
    if action == 'settings':
        settings = load_settings()
        response = {
            "action": "settings",
            "reminder_minutes": settings.get('reminder_minutes', 60),
            "zoom_link": settings.get('zoom_link', '')
        }
        await send_response(response)
        return
