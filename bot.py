import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from database import (
    get_user, update_user, add_diary_entry,
    update_streak, get_week_diary
)
from gemini import chat_with_gemini, generate_weekly_report, generate_motivation_quote
from scheduler import setup_scheduler

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН")
RENDER_URL = os.getenv("RENDER_URL", "")  # https://trainer-bot.onrender.com

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_MOOD, WAITING_ENERGY, WAITING_NOTES = 1, 2, 3

CRISIS_WORDS = [
    "всё плохо", "все плохо", "устал", "не могу", "сдаюсь",
    "депрессия", "грустно", "тяжело", "хочу всё бросить",
    "нет сил", "опустились руки", "расстроен", "не получается",
    "ничего не хочу", "всё надоело", "бросить всё"
]

def main_menu():
    keyboard = [
        [KeyboardButton("✅ Задание выполнено"), KeyboardButton("📓 Дневник")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("💊 Показатели здоровья")],
        [KeyboardButton("🔥 Мой стрик"), KeyboardButton("📈 Отчёт за неделю")],
        [KeyboardButton("💬 Просто поговорить"), KeyboardButton("💡 Мотивация")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "Чемпион"
    get_user(user_id)
    update_user(user_id, {"name": name})
    welcome = await chat_with_gemini(
        user_id, f"Привет! Меня зовут {name}.",
        extra_context=(
            "Первый запуск. Поприветствуй тепло и по-дружески. "
            "Ты — Макс, личный тренер и друг. "
            "Кратко: задания в 7:00, чекин в 21:00, дневник, аналитика. "
            "Спроси главную цель на месяц. Будь живым!"
        )
    )
    await update.message.reply_text(f"👋 {welcome}", reply_markup=main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Что умеет Макс:*\n\n"
        "☀️ 7:00 — задание на день\n"
        "💧 12:00 и 15:00 — напоминание о воде\n"
        "🌙 21:00 — вечерний чекин\n"
        "📊 Вс 20:00 — отчёт за неделю\n\n"
        "*Команды:*\n"
        "`/mood 7` — быстрая оценка настроения\n"
        "`/goal` — поставить новую цель\n"
        "`/cancel` — отменить действие\n\n"
        "*Лайфхаки:*\n"
        "Напиши `вес 80`, `пульс 62`, `сон 7` — сохранится автоматически\n"
        "Плохо на душе — просто напиши, Макс поймёт 🤝"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def quick_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Пример: `/mood 7`", parse_mode="Markdown")
        return
    mood = int(args[0])
    if not 1 <= mood <= 10:
        await update.message.reply_text("Цифра от 1 до 10")
        return
    add_diary_entry(user_id, {"mood": mood, "energy": None, "notes": "быстрая оценка"})
    level = "низкое 😔" if mood <= 4 else "среднее 😐" if mood <= 6 else "хорошее 😊"
    extra = f"Пользователь быстро оценил настроение: {mood}/10 ({level}). Коротко отреагируй — 1 предложение."
    response = await chat_with_gemini(user_id, f"Настроение {mood}/10", extra_context=extra)
    await update.message.reply_text(response, reply_markup=main_menu())

async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    response = await chat_with_gemini(
        user_id, "Хочу поставить новую цель",
        extra_context="Пользователь хочет поставить или обновить цель. Спроси что именно он хочет достичь, за какой срок, и что мешало раньше. Задай 1-2 вопроса."
    )
    await update.message.reply_text(response, reply_markup=main_menu())

async def handle_task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    streak = update_streak(user_id, done=True)
    milestones = {7: "Неделя без пропусков 🎯", 14: "Две недели огня 🔥", 30: "Месяц дисциплины 🏆", 100: "100 дней — легенда 👑"}
    milestone_text = f"\n\n🏆 *{milestones[streak]}* — это реально круто!" if streak in milestones else ""
    extra = (
        f"Пользователь выполнил задание! Стрик: {streak} дней подряд. "
        f"Похвали искренне, по-дружески, без занудства. "
        f"{'Особо отметь веху ' + str(streak) + ' дней!' if streak in milestones else ''}"
    )
    response = await chat_with_gemini(user_id, "Я выполнил задание!", extra_context=extra)
    fires = "🔥" * min(streak // 7 + 1, 5)
    await update.message.reply_text(
        f"{response}{milestone_text}\n\n{fires} Стрик: *{streak} дней!*",
        parse_mode="Markdown", reply_markup=main_menu()
    )

async def handle_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    streak = user.get("streak", 0)
    last_done = user.get("last_task_done", "—")
    if streak == 0:
        text = "🔥 Стрик: 0 дней\n\nНачни сегодня — выполни задание! 💪"
    elif streak < 7:
        text = f"🔥 Стрик: *{streak} дней!*\nПоследнее: {last_done}\nДо недели: {7 - streak} дней"
    elif streak < 30:
        text = f"🔥🔥 Стрик: *{streak} дней!*\nПоследнее: {last_done}\nСерьёзный результат!"
    else:
        text = f"🔥🔥🔥 СТРИК: *{streak} ДНЕЙ!*\nЭто уже образ жизни 🚀"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    diary = get_week_diary(user_id)
    streak = user.get("streak", 0)
    health = user.get("health_data", {})
    moods = [e.get("mood") for e in diary if e.get("mood")]
    energies = [e.get("energy") for e in diary if e.get("energy")]
    avg_mood = round(sum(moods) / len(moods), 1) if moods else "—"
    avg_energy = round(sum(energies) / len(energies), 1) if energies else "—"
    text = (
        f"📊 *Твоя статистика*\n\n"
        f"🔥 Стрик: {streak} дней подряд\n"
        f"😊 Среднее настроение (7 дней): {avg_mood}/10\n"
        f"⚡ Средняя энергия (7 дней): {avg_energy}/10\n"
        f"⚖️ Вес: {health.get('weight', 'не указан')}\n"
        f"📅 Записей в дневнике: {len(user.get('diary', []))}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def handle_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    health = get_user(user_id).get("health_data", {})
    if not health:
        text = (
            "💊 *Показатели здоровья*\n\nПока ничего нет.\n\n"
            "Просто напиши:\n`вес 78` / `пульс 62` / `давление 120/80` / `сон 7`"
        )
    else:
        emoji_map = {"weight": "⚖️ Вес", "pulse": "❤️ Пульс", "pressure": "🩺 Давление", "sleep": "😴 Сон"}
        lines = ["💊 *Мои показатели:*\n"]
        for k, v in health.items():
            lines.append(f"{emoji_map.get(k, k)}: {v}")
        text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def handle_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("⏳ Генерирую отчёт за неделю...")
    report = generate_weekly_report(user_id)
    await update.message.reply_text(report, parse_mode="Markdown", reply_markup=main_menu())

async def handle_motivation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("⚡ Сейчас зарядим...")
    quote = await generate_motivation_quote(user_id)
    await update.message.reply_text(quote, reply_markup=main_menu())

async def handle_talk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    response = await chat_with_gemini(
        user_id, "Хочу просто поговорить",
        extra_context="Пользователь хочет поговорить. Спроси как дела, что на душе. Будь как настоящий друг."
    )
    await update.message.reply_text(response, reply_markup=main_menu())

# ——— ДНЕВНИК ———
async def start_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📓 *Дневник*\n\nОцени настроение от 1 до 10:\n1-3 😔  4-6 😐  7-10 😊",
        parse_mode="Markdown"
    )
    return WAITING_MOOD

async def diary_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mood = int(update.message.text.strip())
        if not 1 <= mood <= 10: raise ValueError
        context.user_data["diary_mood"] = mood
        await update.message.reply_text("⚡ Уровень энергии от 1 до 10:\n1-3 🥱  4-6 ⚡  7-10 🚀")
        return WAITING_ENERGY
    except ValueError:
        await update.message.reply_text("Число от 1 до 10:")
        return WAITING_MOOD

async def diary_energy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        energy = int(update.message.text.strip())
        if not 1 <= energy <= 10: raise ValueError
        context.user_data["diary_energy"] = energy
        await update.message.reply_text("✍️ Заметка (что случилось, как тренировка)?\nИли «-» чтобы пропустить:")
        return WAITING_NOTES
    except ValueError:
        await update.message.reply_text("Число от 1 до 10:")
        return WAITING_ENERGY

async def diary_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = update.message.text.strip()
    if notes == "-": notes = ""
    mood = context.user_data.get("diary_mood")
    energy = context.user_data.get("diary_energy")
    add_diary_entry(user_id, {"mood": mood, "energy": energy, "notes": notes})
    extra = (
        f"Записал в дневник: настроение {mood}/10, энергия {energy}/10"
        f"{', заметка: ' + notes if notes else ''}. "
        f"Коротко отреагируй как друг — 1-2 предложения."
    )
    response = await chat_with_gemini(user_id, "Записал в дневник", extra_context=extra)
    await update.message.reply_text(f"✅ Записано!\n\n{response}", reply_markup=main_menu())
    return ConversationHandler.END

async def cancel_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=main_menu())
    return ConversationHandler.END

# ——— Парсинг данных здоровья ———
def parse_health_data(text: str) -> dict:
    import re
    data = {}
    t = text.lower()
    if m := re.search(r'вес[:\s]+(\d+[\.,]?\d*)', t): data["weight"] = m.group(1) + " кг"
    if m := re.search(r'пульс[:\s]+(\d+)', t): data["pulse"] = m.group(1) + " уд/мин"
    if m := re.search(r'сон[:\s]+(\d+[\.,]?\d*)', t): data["sleep"] = m.group(1) + " ч"
    if m := re.search(r'давлени[еяю][:\s]+(\d+/\d+)', t): data["pressure"] = m.group(1)
    return data

def is_crisis_message(text: str) -> bool:
    return any(w in text.lower() for w in CRISIS_WORDS)

# ——— ГЛАВНЫЙ ОБРАБОТЧИК ———
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    button_map = {
        "✅ Задание выполнено": handle_task_done,
        "📊 Статистика": handle_stats,
        "💊 Показатели здоровья": handle_health,
        "🔥 Мой стрик": handle_streak,
        "📈 Отчёт за неделю": handle_weekly_report,
        "💡 Мотивация": handle_motivation,
        "💬 Просто поговорить": handle_talk,
    }
    if text in button_map:
        await button_map[text](update, context)
        return

    health_data = parse_health_data(text)
    if health_data:
        existing = get_user(user_id).get("health_data", {})
        existing.update(health_data)
        update_user(user_id, {"health_data": existing})

    extra = ""
    if is_crisis_message(text):
        extra = (
            "ВАЖНО: пользователь в подавленном состоянии. "
            "Сначала только выслушай и поддержи — никаких советов. "
            "Дай понять что ты рядом и что это нормально. "
            "Тон: тёплый, живой, как лучший друг."
        )
    elif health_data:
        extra = f"Пользователь поделился данными о здоровье: {health_data}. Прокомментируй коротко."

    response = await chat_with_gemini(user_id, text, extra_context=extra)
    await update.message.reply_text(response, reply_markup=main_menu())

# ——— ЗАПУСК ———
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    diary_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📓 Дневник$"), start_diary)],
        states={
            WAITING_MOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_mood)],
            WAITING_ENERGY: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_energy)],
            WAITING_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_notes)],
        },
        fallbacks=[CommandHandler("cancel", cancel_diary)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mood", quick_mood))
    app.add_handler(CommandHandler("goal", set_goal))
    app.add_handler(diary_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    setup_scheduler(app, app.bot)

    if RENDER_URL:
        logger.info("Webhook режим")
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 10000)),
            webhook_url=f"{RENDER_URL}/webhook"
        )
    else:
        logger.info("Polling режим (локально)")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
