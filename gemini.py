import google.generativeai as genai
import warnings
warnings.filterwarnings("ignore")
from database import get_user, add_to_history, get_week_diary
from datetime import date
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY", "ВАШ_КЛЮЧ"))
model = genai.GenerativeModel("gemini-1.5-flash")

SYSTEM_PROMPT = """
Ты — личный тренер, наставник и друг по имени Макс. Общаешься на русском языке.

Роли:
1. ТРЕНЕР — конкретные задания по фитнесу, питанию, режиму. Адаптируешь нагрузку.
2. НАСТАВНИК — мотивируешь, помогаешь не сдаваться, работаешь с прокрастинацией.
3. ДРУГ — когда человек делится неудачами, сначала поддерживаешь. Без банальщины.
4. АНАЛИТИК — замечаешь паттерны в настроении и физическом состоянии.
5. ДНЕВНИК — помогаешь рефлексировать и видеть прогресс.

Стиль:
- Живой, дружелюбный, иногда с лёгким юмором
- Не занудный и не казённый
- Краткие ответы когда уместно, развёрнутые когда нужна поддержка
- Эмодзи умеренно
- Помни контекст — ты знаешь историю человека

Главное: когда человек говорит о неудаче или плохом дне — СНАЧАЛА поддержи, советы потом.
"""

def _build_history_text(history: list) -> str:
    if not history:
        return ""
    lines = []
    for msg in history[-10:]:
        role = "Пользователь" if msg["role"] == "user" else "Макс"
        text = msg["parts"][0] if isinstance(msg["parts"], list) else msg["parts"]
        lines.append(f"{role}: {text}")
    return "\n".join(lines)

def _build_user_context(user: dict) -> str:
    ctx = "О пользователе:\n"
    if user.get("name"): ctx += f"- Имя: {user['name']}\n"
    ctx += f"- Стрик: {user.get('streak', 0)} дней подряд\n"
    if user.get("health_data"): ctx += f"- Здоровье: {user['health_data']}\n"
    return ctx

def _summarize_diary(diary: list) -> str:
    if not diary: return "Данных нет"
    lines = []
    for e in diary[-7:]:
        line = f"{e.get('date','')}: настроение={e.get('mood','?')}/10, энергия={e.get('energy','?')}/10"
        if e.get("notes"): line += f", {e['notes'][:40]}"
        lines.append(line)
    return "\n".join(lines)

async def chat_with_gemini(user_id: int, user_message: str, extra_context: str = "") -> str:
    user = get_user(user_id)
    history = user.get("history", [])
    user_context = _build_user_context(user)
    history_text = _build_history_text(history)

    prompt = f"{SYSTEM_PROMPT}\n\n{user_context}"
    if history_text:
        prompt += f"\n\nИстория диалога:\n{history_text}"
    if extra_context:
        prompt += f"\n\nКонтекст: {extra_context}"
    prompt += f"\n\nПользователь: {user_message}\nМакс:"

    try:
        response = model.generate_content(prompt)
        reply = response.text
        add_to_history(user_id, "user", user_message)
        add_to_history(user_id, "model", reply)
        return reply
    except Exception as e:
        return f"Упс, что-то пошло не так: {e}"

def generate_daily_task(user_id: int) -> str:
    user = get_user(user_id)
    streak = user.get("streak", 0)
    diary = get_week_diary(user_id)
    health = user.get("health_data", {})

    prompt = f"""
{SYSTEM_PROMPT}

Данные:
- Стрик: {streak} дней
- Последние дни: {_summarize_diary(diary)}
- Здоровье: {health}

Сгенерируй задание на {date.today().strftime('%A, %d %B')}.
Включи:
1. Физическое упражнение (конкретное, с цифрами)
2. Один habit (питание, вода, сон)
3. Ментальное задание (чтение, медитация, отложенное дело)

Тон: бодро, по-дружески. Стрик {streak} — упомяни если > 3.
Максимум 5-6 строк.
"""
    try:
        return model.generate_content(prompt).text
    except Exception as e:
        return "Доброе утро! 💪 Сегодня: 30 мин активности + 2 литра воды + одно откладываемое дело."

def generate_evening_checkin(user_id: int) -> str:
    user = get_user(user_id)
    task = user.get("current_task", "задание дня")
    streak = user.get("streak", 0)

    prompt = f"""
{SYSTEM_PROMPT}

Задание было: {task}
Стрик: {streak} дней.

Напиши вечерний чекин — дружески спроси:
1. Выполнил ли задание (или что удалось)
2. Как самочувствие и настроение
3. Одну хорошую вещь которая случилась сегодня

Тон: тёплый, как друг. 3-4 строки.
"""
    try:
        return model.generate_content(prompt).text
    except:
        return "Привет! 🌙 Как прошёл день? Удалось выполнить задание? Расскажи что хорошего случилось 😊"

def generate_weekly_report(user_id: int) -> str:
    user = get_user(user_id)
    diary = get_week_diary(user_id)
    streak = user.get("streak", 0)
    health = user.get("health_data", {})

    prompt = f"""
{SYSTEM_PROMPT}

Данные за неделю:
{_summarize_diary(diary)}
Стрик: {streak} дней
Здоровье: {health}

Сделай аналитический отчёт:
1. Общий итог (настроение, энергия, выполнение)
2. Что идёт хорошо
3. Что улучшить на следующей неделе
4. Один инсайт о паттернах
5. Мотивирующий финал

Стиль: аналитично но тепло.
"""
    try:
        return f"📊 *Итоги недели*\n\n{model.generate_content(prompt).text}"
    except:
        return "📊 Неделя позади! Ты молодец что продолжаешь — это главное 💪"

async def generate_motivation_quote(user_id: int) -> str:
    user = get_user(user_id)
    streak = user.get("streak", 0)
    diary = get_week_diary(user_id)
    moods = [e.get("mood") for e in diary if e.get("mood")]
    avg_mood = round(sum(moods) / len(moods), 1) if moods else 5

    prompt = f"""
{SYSTEM_PROMPT}

Пользователь хочет заряд мотивации.
Стрик: {streak} дней. Среднее настроение: {avg_mood}/10.

Дай:
1. Мощную цитату (реальную или в похожем стиле)
2. 2-3 предложения от себя — персональный заряд с учётом стрика и настроения

Тон: энергичный, вдохновляющий. Не банально.
"""
    try:
        return f"💡 {model.generate_content(prompt).text}"
    except:
        return "💡 Дисциплина — это выбор между тем чего хочешь сейчас и тем чего хочешь больше всего. Вперёд! 🚀"

def ask_health_question(user_id: int) -> str:
    import random
    health = get_user(user_id).get("health_data", {})
    questions = [
        "Сколько примерно весишь сейчас? Хочу отслеживать динамику 📈",
        "Как со сном? Сколько часов в среднем и чувствуешь ли себя отдохнувшим?",
        "Как пульс в покое? Если знаешь — напиши, буду следить ❤️",
        "Как с водой сегодня? Сколько выпил литров?",
        "Есть что-то что болит или беспокоит физически?",
        "Как уровень энергии в течение дня — стабильный или скачет?",
    ]
    if "weight" not in health: return questions[0]
    if "sleep" not in health: return questions[1]
    return random.choice(questions[2:])
