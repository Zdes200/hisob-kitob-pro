import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import os
TOKEN = os.getenv("TOKEN")

tz = ZoneInfo("Asia/Tashkent")

# ===== DATABASE =====
conn = sqlite3.connect("finance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    category TEXT,
    note TEXT,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    person TEXT,
    amount INTEGER,
    type TEXT,
    due_date TEXT
)
""")

conn.commit()

# ===== STATE =====
user_state = {}

def now():
    return datetime.now(tz)

def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["💰 Balans", "➕ Xarajat"],
            ["💳 Qarz"],
            ["📅 Bugungi", "📆 Oylik", "📊 Yillik"]
        ],
        resize_keyboard=True
    )

def back_menu():
    return ReplyKeyboardMarkup([["🔙 Orqaga"]], resize_keyboard=True)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id] = None
    await update.message.reply_text(
        "💎 HISOB KITOB PRO\nBalans • Xarajat • Qarz • Hisobot",
        reply_markup=main_menu()
    )

# ===== HANDLER =====
async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ORQAGA
    if text == "🔙 Orqaga":
        user_state[user_id] = None
        await update.message.reply_text("Asosiy menyu", reply_markup=main_menu())
        return

    # ===== BALANS =====
    if text == "💰 Balans":
        user_state[user_id] = "balance"
        await update.message.reply_text("Balans summasini yozing:", reply_markup=back_menu())
        return

    if user_state.get(user_id) == "balance" and text.isdigit():
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, balance) VALUES (?,?)",
            (user_id, int(text))
        )
        conn.commit()
        user_state[user_id] = None
        await update.message.reply_text("Balans saqlandi", reply_markup=main_menu())
        return

    # ===== XARAJAT =====
    if text == "➕ Xarajat":
        user_state[user_id] = "expense"
        await update.message.reply_text(
            "Format:\n25000 transport metro",
            reply_markup=back_menu()
        )
        return

    if user_state.get(user_id) == "expense":
        parts = text.split()
        if len(parts) >= 2 and parts[0].isdigit():
            amount = int(parts[0])
            category = parts[1]
            note = " ".join(parts[2:]) if len(parts) > 2 else "-"

            cursor.execute("""
            INSERT INTO expenses (user_id, amount, category, note, date)
            VALUES (?,?,?,?,?)
            """, (user_id, amount, category, note, now_str()))
            conn.commit()

            user_state[user_id] = None
            await update.message.reply_text("Xarajat qo‘shildi", reply_markup=main_menu())
        return

    # ===== QARZ =====
    if text == "💳 Qarz":
        user_state[user_id] = "debt_type"
        await update.message.reply_text(
            "Yozing:\nberildi yoki olindi",
            reply_markup=back_menu()
        )
        return

    if user_state.get(user_id) == "debt_type" and text in ["berildi", "olindi"]:
        user_state[user_id] = text
        await update.message.reply_text(
            "Format:\nAli 100000 2",
            reply_markup=back_menu()
        )
        return

    if user_state.get(user_id) in ["berildi", "olindi"]:
        parts = text.split()
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            person = parts[0]
            amount = int(parts[1])
            days = int(parts[2])
            due = now() + timedelta(days=days)

            cursor.execute("""
            INSERT INTO debts (user_id, person, amount, type, due_date)
            VALUES (?,?,?,?,?)
            """, (
                user_id,
                person,
                amount,
                user_state[user_id],
                due.strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()

            user_state[user_id] = None
            await update.message.reply_text("Qarz saqlandi", reply_markup=main_menu())
        return

    # ===== HISOBOT =====
    if text in ["📅 Bugungi", "📆 Oylik", "📊 Yillik"]:
        if text == "📅 Bugungi":
            pattern = now().strftime("%Y-%m-%d") + "%"
        elif text == "📆 Oylik":
            pattern = now().strftime("%Y-%m") + "%"
        else:
            pattern = now().strftime("%Y") + "%"

        cursor.execute("""
        SELECT SUM(amount) FROM expenses
        WHERE user_id=? AND date LIKE ?
        """, (user_id, pattern))

        total = cursor.fetchone()[0] or 0

        await update.message.reply_text(
            f"{text}: {total} UZS\n{now_str()}",
            reply_markup=main_menu()
        )

# ===== QARZ REMINDER =====
def debt_check():
    current = now_str()
    cursor.execute("""
    SELECT id, user_id, person, amount, due_date
    FROM debts
    WHERE due_date <= ?
    """, (current,))
    rows = cursor.fetchall()

    for row in rows:
        debt_id, uid, person, amount, due = row
        try:
            app.bot.send_message(
                chat_id=uid,
                text=f"🔔 QARZ MUDDATI!\n{person}\n{amount} UZS\n{due}"
            )
        except:
            pass

        cursor.execute("DELETE FROM debts WHERE id=?", (debt_id,))
        conn.commit()

scheduler = BackgroundScheduler(timezone=tz)
scheduler.add_job(debt_check, "interval", minutes=1)
scheduler.start()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

print("Bot ishga tushdi...")
app.run_polling()
