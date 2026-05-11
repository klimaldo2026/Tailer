from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

TIMEZONE = "Asia/Almaty"  # UTC+5, Казахстан. Поменяй если нужно.

def setup_scheduler(app, bot):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 7:00 — утреннее задание
    scheduler.add_job(send_morning_task, CronTrigger(hour=7, minute=0, timezone=TIMEZONE), args=[bot])
    # 12:00 — напоминание о воде
    scheduler.add_job(send_water_reminder, CronTrigger(hour=12, minute=0, timezone=TIMEZONE), args=[bot, "обед"])
    # 15:00 — напоминание о воде
    scheduler.add_job(send_water_reminder, CronTrigger(hour=15, minute=0, timezone=TIMEZONE), args=[bot, "день"])
    # 21:00 — вечерний чекин
    scheduler.add_job(send_evening_checkin, CronTrigger(hour=21, minute=0, timezone=TIMEZONE), args=[bot])
    # Воскресенье 20:00 — недельный отчёт
    scheduler.add_job(send_weekly_report, CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=TIMEZONE), args=[bot])
    # Каждые 3 дня 13:00 — вопрос о здоровье
    scheduler.add_job(send_health_question, CronTrigger(day="*/3", hour=13, minute=0, timezone=TIMEZONE), args=[bot])
    # Полночь — сброс флагов
    scheduler.add_job(reset_daily_flags, CronTrigger(hour=0, minute=0, timezone=TIMEZONE), args=[bot])

    scheduler.start()
    return scheduler

async def send_morning_task(bot):
    from database import get_all_users, update_user
    from gemini import generate_daily_task
    for uid in get_all_users():
        try:
            task = generate_daily_task(int(uid))
            update_user(int(uid), {"current_task": task, "task_done_today": False})
            from database import get_user
            streak = get_user(int(uid)).get("streak", 0)
            streak_text = f"\n\n🔥 Стрик: {streak} дней подряд!" if streak >= 3 else ""
            await bot.send_message(
                chat_id=int(uid),
                text=f"☀️ *Доброе утро! Задание на сегодня:*\n\n{task}{streak_text}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Ошибка утреннего задания {uid}: {e}")

async def send_water_reminder(bot, time_of_day: str):
    from database import get_all_users
    import random
    messages = [
        "💧 Эй, ты пил воду сегодня? Стакан прямо сейчас — обязательно!",
        "💧 Вода — это не опция, это программа. Выпей стакан!",
        "💧 Гидратация = энергия. Сделай перерыв и выпей воды 🥤",
    ]
    for uid in get_all_users():
        try:
            await bot.send_message(chat_id=int(uid), text=random.choice(messages))
        except Exception as e:
            print(f"Ошибка напоминания воды {uid}: {e}")

async def send_evening_checkin(bot):
    from database import get_all_users
    from gemini import generate_evening_checkin
    for uid in get_all_users():
        try:
            checkin = generate_evening_checkin(int(uid))
            await bot.send_message(chat_id=int(uid), text=f"🌙 {checkin}", parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка вечернего чекина {uid}: {e}")

async def send_weekly_report(bot):
    from database import get_all_users
    from gemini import generate_weekly_report
    for uid in get_all_users():
        try:
            report = generate_weekly_report(int(uid))
            await bot.send_message(chat_id=int(uid), text=report, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка недельного отчёта {uid}: {e}")

async def send_health_question(bot):
    from database import get_all_users
    from gemini import ask_health_question
    import random
    for uid in get_all_users():
        try:
            if random.random() < 0.6:
                question = ask_health_question(int(uid))
                await bot.send_message(chat_id=int(uid), text=f"💊 {question}")
        except Exception as e:
            print(f"Ошибка вопроса здоровья {uid}: {e}")

async def reset_daily_flags(bot):
    from database import get_all_users, reset_daily
    for uid in get_all_users():
        try:
            reset_daily(int(uid))
        except Exception as e:
            print(f"Ошибка сброса {uid}: {e}")
