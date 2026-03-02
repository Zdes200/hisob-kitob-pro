import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

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
    name TEXT,
    amount INTEGER,
    date TEXT
)
""")

conn.commit()

# ===== HELPERS =====
def now():
    return datetime.now(tz)

def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")

def format_money(x):
    return f"{x:,}".replace(",", " ")

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def total_expense(user_id):
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0]
    return total if total else 0

def remaining(user_id):
    return get_balance(user_id) - total_expense(user_id)

# ===== MENU =====
def menu():
    return ReplyKeyboardMarkup(
        [
            ["💰 Pul qo‘shish", "📊 Balans"],
            ["📋 Xarajatlar", "📆 Oylik"]
        ],
        resize_keyboard=True
    )

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 HISOB KITOB PRO 2.0\n\n"
        "Pul qo‘shing yoki xarajat yozing.\n"
        "Masalan:\n1000 qurut",
        reply_markup=menu()
    )

# ===== HANDLER =====
async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # 💰 Pul qo‘shish
    if text == "💰 Pul qo‘shish":
        await update.message.reply_text("Summani yozing:")
        return

    if text.isdigit():
        amount = int(text)
        current = get_balance(user_id)
        new_balance = current + amount

        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, balance) VALUES (?,?)",
            (user_id, new_balance)
        )
        conn.commit()

        await update.message.reply_text(
            f"💵 Pul qo‘shildi: {format_money(amount)} UZS\n"
            f"💳 Yangi balans: {format_money(new_balance)} UZS",
            reply_markup=menu()
        )
        return

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
            f"➖ Xarajat qo‘shildi\n\n"
            f"📦 Nomi: {name.capitalize()}\n"
            f"💰 Summa: {format_money(amount)} UZS\n"
            f"🕒 {now_str()}\n\n"
            f"💳 Qolgan balans: {format_money(remaining(user_id))} UZS",
            reply_markup=menu()
        )
        return

    # 📊 Balans
    if text == "📊 Balans":
        await update.message.reply_text(
            f"💰 Boshlang‘ich: {format_money(get_balance(user_id))} UZS\n"
            f"➖ Xarajat: {format_money(total_expense(user_id))} UZS\n"
            f"💳 Qolgan: {format_money(remaining(user_id))} UZS",
            reply_markup=menu()
        )
        return

    # 📋 Xarajatlar
    if text == "📋 Xarajatlar":
        cursor.execute("""
        SELECT id, name, amount, date 
        FROM expenses 
        WHERE user_id=? 
        ORDER BY id DESC 
        LIMIT 10
        """, (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Xarajat yo‘q", reply_markup=menu())
            return

        msg = "📋 So‘nggi xarajatlar:\n\n"
        for i, (eid, name, amount, date) in enumerate(rows, 1):
            msg += f"{i}) {name.capitalize()} — {format_money(amount)} UZS\n"
            msg += f"   🕒 {date}\n"
            msg += f"   🆔 ID: {eid}\n\n"

        msg += "🗑 O‘chirish: del ID\n✏ Tahrirlash: edit ID summa nom"

        await update.message.reply_text(msg, reply_markup=menu())
        return

    # 🗑 O‘chirish
    if text.startswith("del "):
        try:
            eid = int(text.split()[1])
            cursor.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (eid, user_id))
            conn.commit()

            await update.message.reply_text(
                f"🗑 Xarajat o‘chirildi\n💳 Qolgan: {format_money(remaining(user_id))} UZS",
                reply_markup=menu()
            )
        except:
            await update.message.reply_text("Xato ID", reply_markup=menu())
        return

    # ✏ Tahrirlash
    if text.startswith("edit "):
        parts = text.split()
        if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
            eid = int(parts[1])
            amount = int(parts[2])
            name = " ".join(parts[3:])

            cursor.execute("""
            UPDATE expenses 
            SET amount=?, name=? 
            WHERE id=? AND user_id=?
            """, (amount, name, eid, user_id))
            conn.commit()

            await update.message.reply_text(
                f"✏ Yangilandi\n💳 Qolgan: {format_money(remaining(user_id))} UZS",
                reply_markup=menu()
            )
        return

    # 📆 Oylik hisobot
    if text == "📆 Oylik":
        month = now().strftime("%Y-%m")

        cursor.execute("""
        SELECT name, amount, date 
        FROM expenses 
        WHERE user_id=? AND date LIKE ?
        """, (user_id, month + "%"))

        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Bu oy xarajat yo‘q", reply_markup=menu())
            return

        total = 0
        msg = "📆 Oylik hisobot:\n\n"

        for name, amount, date in rows:
            total += amount
            short_date = date[8:10] + "-" + date[5:7]
            msg += f"• {name.capitalize()} — {format_money(amount)} UZS ({short_date})\n"

        msg += f"\n💸 Jami: {format_money(total)} UZS\n"
        msg += f"💳 Qolgan: {format_money(remaining(user_id))} UZS"

        await update.message.reply_text(msg, reply_markup=menu())
        return

# ===== 24 SOATLIK HISOBOT =====
def daily_report():
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    today = now().strftime("%Y-%m-%d")

    for (uid,) in users:
        cursor.execute("""
        SELECT name, amount FROM expenses
        WHERE user_id=? AND date LIKE ?
        """, (uid, today + "%"))

        rows = cursor.fetchall()
        if not rows:
            continue

        total = sum(r[1] for r in rows)

        msg = "📊 24 Soatlik Hisobot\n\n"
        for name, amount in rows:
            msg += f"• {name.capitalize()} — {format_money(amount)} UZS\n"

        msg += f"\n💸 Bugungi jami: {format_money(total)} UZS\n"
        msg += f"💳 Qolgan balans: {format_money(remaining(uid))} UZS\n"
        msg += f"🕒 {now_str()}"

        try:
            app.bot.send_message(chat_id=uid, text=msg)
        except:
            pass

scheduler = BackgroundScheduler(timezone=tz)
scheduler.add_job(daily_report, "cron", hour=23, minute=59)
scheduler.start()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

print("Bot ishga tushdi...")
app.run_polling()
