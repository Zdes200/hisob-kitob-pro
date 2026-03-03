import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
tz = ZoneInfo("Asia/Tashkent")

# ===== DATABASE =====
conn = sqlite3.connect("finance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    amount INTEGER,
    date TEXT
)
""")
conn.commit()

# ===== MENU =====
def menu():
    return ReplyKeyboardMarkup(
        [
            ["📅 Kunlik", "📆 Oylik"]
        ],
        resize_keyboard=True
    )

def now():
    return datetime.now(tz)

def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")

def format_money(x):
    return f"{x:,}".replace(",", " ")

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Xarajat yozing.\n\n"
        "Masalan:\n"
        "1000 qurut",
        reply_markup=menu()
    )

# ===== HANDLER =====
async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ➖ Xarajat qo‘shish
    parts = text.split()
    if len(parts) >= 2 and parts[0].isdigit():
        amount = int(parts[0])
        name = " ".join(parts[1:])

        cursor.execute("""
        INSERT INTO expenses (user_id, name, amount, date)
        VALUES (?, ?, ?, ?)
        """, (user_id, name, amount, now_str()))
        conn.commit()

        await update.message.reply_text(
            f"➖ {name.capitalize()} — {format_money(amount)} UZS\n"
            f"🕒 {now_str()}",
            reply_markup=menu()
        )
        return

    # 📅 Kunlik
    if text == "📅 Kunlik":
        today = now().strftime("%Y-%m-%d")

        cursor.execute("""
        SELECT name, amount, date FROM expenses
        WHERE user_id=? AND date LIKE ?
        """, (user_id, today + "%"))

        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Bugun xarajat yo‘q", reply_markup=menu())
            return

        total = 0
        msg = "📅 Bugungi xarajatlar:\n\n"

        for name, amount, date in rows:
            total += amount
            time_only = date[11:16]
            msg += f"• {name.capitalize()} — {format_money(amount)} UZS\n"
            msg += f"  🕒 {time_only}\n\n"

        msg += f"💸 Jami: {format_money(total)} UZS"

        await update.message.reply_text(msg, reply_markup=menu())
        return

    # 📆 Oylik
    if text == "📆 Oylik":
        month = now().strftime("%Y-%m")

        cursor.execute("""
        SELECT name, amount, date FROM expenses
        WHERE user_id=? AND date LIKE ?
        """, (user_id, month + "%"))

        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Bu oy xarajat yo‘q", reply_markup=menu())
            return

        total = 0
        msg = "📆 Oylik xarajatlar:\n\n"

        for name, amount, date in rows:
            total += amount
            short_date = date[8:10] + "-" + date[5:7]
            msg += f"• {name.capitalize()} — {format_money(amount)} UZS ({short_date})\n"

        msg += f"\n💸 Jami: {format_money(total)} UZS"

        await update.message.reply_text(msg, reply_markup=menu())
        return

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

print("Bot ishga tushdi...")
app.run_polling(drop_pending_updates=True, close_loop=False)
