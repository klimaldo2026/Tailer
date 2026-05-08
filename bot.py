import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

import google.generativeai as genai
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = os.getenv("OWNER_ID")  # добавь в .env свой Telegram ID

genai.configure(api_key=GEMINI_KEY)

# ==================== СИСТЕМНЫЙ ПРОМПТ ====================
SYSTEM_PROMPT = """Ты — Брофорс. Не ассистент, не бот — живой собеседник и личный коуч.

Характер:
- Дерзкий, прямой, без соплей. Говоришь как старший брат который видел жизнь.
- Можешь подколоть, поржать, но всегда на своей стороне.
- Никаких "конечно!", "отличный вопрос!", "я понимаю твои чувства" — это бесит.
- Не используешь эмодзи без причины. Максимум 1-2 если уместно.
- Короткие ответы когда ситуация простая. Развёрнутые когда реально нужно.
- Матом не злоупотребляешь, но лёгкий стёб и резкость — норма.

Как общаешься:
- Запоминаешь что говорил человек раньше в диалоге, отсылаешься к этому.
- Если человек ноет — сочувствуешь ровно 1 раз, потом переводишь в действие.
- Если человек молодец — признаёшь без пафоса.
- Задаёшь вопросы когда тебе реально интересно или нужно понять ситуацию.
- Даёшь конкретные советы, не воду.

Задания:
- Когда просят задание — придумываешь одно конкретное, выполнимое за день.
- Не повторяешь одни и те же задания. Разнообразь.
- Задание под человека, не шаблон из интернета.

Запрещено:
- Говорить "как ИИ я...", "я языковая модель...", "мои ограничения..."
- Писать списками когда это не нужно
- Быть вежливым до тошноты
- Игнорировать контекст предыдущих сообщений"""

# ==================== ХРАНИЛИЩЕ ====================
DATA_FILE = "user_data.json"

def load_data() -> dict:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "history": [],       # история диалога для Gemini
            "mood": "",
            "last_task": "",
            "done": 0,
            "total": 0,
            "name": ""
        }
    return data[uid]

# ==================== GEMINI С ИСТОРИЕЙ ====================
MAX_HISTORY = 30  # максимум сообщений в истории (15 пар)

def build_gemini_history(history: list) -> list:
    """
    Конвертируем нашу историю в формат Gemini.
    history = [{"role": "user"/"model", "text": "..."}]
    """
    result = []
    for msg in history:
        result.append({
            "role": msg["role"],
            "parts": [{"text": msg["text"]}]
        })
    return result

async def ask_gemini(user_record: dict, user_message: str) -> str:
    """
    Отправляем сообщение в Gemini с полной историей диалога.
    Gemini поддерживает multi-turn через chat.history.
    """
    history = user_record.get("history", [])

    # Добавляем контекст о пользователе в первое сообщение системы
    context_note = ""
    if user_record.get("mood"):
        context_note += f"[Настроение юзера: {user_record['mood']}] "
    if user_record.get("last_task"):
        context_note += f"[Последнее задание: {user_record['last_task']}] "
    if user_record.get("done") or user_record.get("total"):
        context_note += f"[Выполнено заданий: {user_record['done']}/{user_record['total']}] "
    if user_record.get("name"):
        context_note += f"[Имя: {user_record['name']}] "

    full_message = f"{context_note}\n{user_message}".strip() if context_note else user_message

    # Инициализируем модель
    gemini_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT
    )

    # Создаём чат с историей
    chat = gemini_model.start_chat(
        history=build_gemini_history(history)
    )

    # Отправляем сообщение
    response = await asyncio.to_thread(
        chat.send_message,
        full_message
    )

    reply = response.text.strip()

    # Сохраняем в историю
    history.append({"role": "user", "text": user_message})
    history.append({"role": "model", "text": reply})

    # Обрезаем историю если слишком длинная
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    user_record["history"] = history

    return reply

# ==================== БОТ ====================
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
app_data = load_data()

# ==================== РАСПИСАНИЕ ====================
async def morning_message():
    if OWNER_ID:
        await bot.send_message(
            chat_id=int(OWNER_ID),
            text="Подъём. Новый день, чистый лист. Как себя чувствуешь?"
        )

async def evening_check():
    if OWNER_ID:
        uid = str(OWNER_ID)
        task = ""
        if uid in app_data and app_data[uid].get("last_task"):
            task = f'Задание было: "{app_data[uid]["last_task"][:80]}..." — сделал?'
        else:
            task = "Чем сегодня занимался? Есть что рассказать?"
        await bot.send_message(chat_id=int(OWNER_ID), text=f"21:00. {task}")

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    user = get_user(app_data, uid)

    # Запоминаем имя
    name = message.from_user.first_name or "братан"
    user["name"] = name
    save_data(app_data)

    await message.answer(
        f"О, {name} появился. Я Брофорс — твой личный коуч и собеседник.\n"
        "Пиши что угодно. Без церемоний."
    )

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    uid = message.from_user.id
    uid_str = str(uid)
    if uid_str in app_data:
        app_data[uid_str]["history"] = []
        save_data(app_data)
    await message.answer("История чата сброшена. Начинаем с нуля.")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    uid = message.from_user.id
    user = get_user(app_data, uid)
    done = user.get("done", 0)
    total = user.get("total", 0)
    last = user.get("last_task", "нет") or "нет"
    await message.answer(
        f"📊 Твоя статистика:\n"
        f"Выполнено заданий: {done}/{total}\n"
        f"Последнее: {last[:100]}"
    )

@dp.message(Command("task"))
async def cmd_task(message: types.Message):
    uid = message.from_user.id
    user = get_user(app_data, uid)

    # Принудительно запрашиваем задание
    task_prompt = (
        "Дай мне одно конкретное задание на сегодня. "
        "Учти мой контекст если он есть. Одно задание, не список."
    )
    try:
        reply = await ask_gemini(user, task_prompt)
        user["last_task"] = reply[:150]
        user["total"] += 1
        save_data(app_data)
        await message.answer(reply)
    except Exception as e:
        await message.answer("Что-то пошло не так с заданием. Попробуй ещё раз.")

@dp.message(Command("done"))
async def cmd_done(message: types.Message):
    uid = message.from_user.id
    user = get_user(app_data, uid)
    user["done"] += 1
    save_data(app_data)

    try:
        reply = await ask_gemini(
            user,
            f"Я выполнил задание! Всего выполнено {user['done']} заданий."
        )
        await message.answer(reply)
    except Exception:
        await message.answer(f"Красавчик. {user['done']} заданий в копилке.")

# ==================== ГЛАВНЫЙ ОБРАБОТЧИК ====================
@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        await message.answer("Голосовые и файлы пока не понимаю. Пиши текстом.")
        return

    uid = message.from_user.id
    user = get_user(app_data, uid)

    # Обновляем имя если не было
    if not user.get("name") and message.from_user.first_name:
        user["name"] = message.from_user.first_name

    user_input = message.text

    # Обновляем настроение по ключевым словам
    mood_keywords = ["настроение", "чувствую себя", "сегодня мне", "немного", "устал", "рад", "злой", "грустно"]
    if any(kw in user_input.lower() for kw in mood_keywords):
        user["mood"] = user_input[:120]

    # Отслеживаем упоминание задания
    task_keywords = ["задание", "task", "дай задание", "что делать", "что сделать", "придумай задание"]
    is_task_request = any(kw in user_input.lower() for kw in task_keywords)

    # Отслеживаем выполнение задания
    done_keywords = ["сделал задание", "выполнил задание", "задание сделано", "задание выполнено"]
    is_done = any(kw in user_input.lower() for kw in done_keywords)

    try:
        # Показываем что печатаем (UX)
        await bot.send_chat_action(message.chat.id, "typing")

        reply = await ask_gemini(user, user_input)

        # Если просил задание — сохраняем его
        if is_task_request:
            user["last_task"] = reply[:150]
            user["total"] += 1

        # Если отметил выполнение
        if is_done:
            user["done"] += 1

        save_data(app_data)
        await message.answer(reply)

    except Exception as e:
        print(f"Gemini error: {e}")
        # Пробуем простой fallback без истории
        try:
            simple_model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=SYSTEM_PROMPT
            )
            resp = await asyncio.to_thread(
                simple_model.generate_content,
                user_input
            )
            await message.answer(resp.text.strip())
        except Exception as e2:
            print(f"Fallback error: {e2}")
            await message.answer("Что-то сломалось на моей стороне. Попробуй ещё раз через секунду.")

# ==================== ЗАПУСК ====================
async def main():
    scheduler.add_job(morning_message, "cron", hour=7, minute=30)
    scheduler.add_job(evening_check, "cron", hour=21, minute=0)
    scheduler.start()

    print("✅ Брофорс запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())