import json
import os
from datetime import datetime, date

DATA_FILE = "data/users.json"

def _load():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id: int) -> dict:
    data = _load()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "name": "",
            "history": [],          # история сообщений для Gemini (последние 20)
            "diary": [],            # дневник: {date, mood, energy, notes}
            "streak": 0,            # текущий стрик выполненных заданий
            "last_task_done": None, # дата последнего выполненного задания
            "weekly_stats": [],     # данные за неделю
            "health_data": {},      # мед показатели: вес, пульс и тд
            "current_task": "",     # задание на сегодня
            "task_done_today": False,
            "created_at": str(date.today()),
        }
        _save(data)
    return data[uid]

def update_user(user_id: int, fields: dict):
    data = _load()
    uid = str(user_id)
    if uid not in data:
        get_user(user_id)
        data = _load()
    data[uid].update(fields)
    _save(data)

def add_diary_entry(user_id: int, entry: dict):
    data = _load()
    uid = str(user_id)
    entry["date"] = str(date.today())
    entry["time"] = datetime.now().strftime("%H:%M")
    data[uid]["diary"].append(entry)
    # Храним последние 90 записей
    data[uid]["diary"] = data[uid]["diary"][-90:]
    _save(data)

def add_to_history(user_id: int, role: str, text: str):
    data = _load()
    uid = str(user_id)
    data[uid]["history"].append({"role": role, "parts": [text]})
    # Храним последние 20 сообщений для контекста
    data[uid]["history"] = data[uid]["history"][-20:]
    _save(data)

def update_streak(user_id: int, done: bool):
    data = _load()
    uid = str(user_id)
    today = str(date.today())
    user = data[uid]
    
    if done:
        last = user.get("last_task_done")
        if last:
            from datetime import timedelta
            last_date = date.fromisoformat(last)
            if (date.today() - last_date).days == 1:
                user["streak"] = user.get("streak", 0) + 1
            elif last == today:
                pass  # уже засчитано
            else:
                user["streak"] = 1  # стрик прерван
        else:
            user["streak"] = 1
        user["last_task_done"] = today
        user["task_done_today"] = True
    else:
        user["task_done_today"] = False
    
    _save(data)
    return user.get("streak", 0)

def get_week_diary(user_id: int) -> list:
    user = get_user(user_id)
    diary = user.get("diary", [])
    # Последние 7 записей
    return diary[-7:]

def reset_daily(user_id: int):
    """Сбрасывает флаг задания на начало нового дня"""
    update_user(user_id, {"task_done_today": False, "current_task": ""})

def get_all_users() -> list:
    data = _load()
    return list(data.keys())
