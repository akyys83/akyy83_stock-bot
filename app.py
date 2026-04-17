import matplotlib
matplotlib.use('Agg')  # ✅ IMPORTANT (for Render)

import yfinance as yf
import pandas as pd
import ta
import time
import requests
from datetime import datetime, time as dt_time, timedelta
import pytz
import os
from flask import Flask
import threading
import matplotlib.pyplot as plt
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# =========================
# 🌐 FLASK
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Stock bot running 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================
# 🔑 TOKEN (PUT YOURS HERE)
# =========================
TELEGRAM_TOKEN = "8331695862:AAGoGIVDY95PncAZXswx3HRcVRrOfRBVR8g"
CHAT_ID = "6368208787"

# =========================
# 🧠 MEMORY
# =========================
active_trades = {}
cooldowns = {}
bot_running = True

dashboard_message_id = None
dashboard_chat_id = None

# =========================
# 📊 CACHE
# =========================
market_data_cache = {}

def get_data(ticker):
    now = time.time()

    if ticker in market_data_cache:
        if now - market_data_cache[ticker]['time'] < 60:
            return market_data_cache[ticker]['data']

    df = yf.download(ticker, interval="5m", period="1d", progress=False)

    market_data_cache[ticker] = {"data": df, "time": now}
    return df

def get_ltp(ticker):
    df = get_data(ticker)
    return float(df['Close'].iloc[-1]) if not df.empty else 0

# =========================
# 🕒 MARKET TIME
# =========================
def is_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    if now.weekday() >= 5:
        return False

    return dt_time(9, 15) <= now.time() <= dt_time(15, 30)

def sleep_until_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    market_start = now.replace(hour=9, minute=15, second=0)

    if now.time() > dt_time(15, 30):
        market_start += timedelta(days=1)

    while market_start.weekday() >= 5:
        market_start += timedelta(days=1)

    time.sleep(max((market_start - now).total_seconds(), 0))

# =========================
# 📲 TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# 📊 UI
# =========================
def get_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard"),
         InlineKeyboardButton("💰 PnL", callback_data="pnl")],
        [InlineKeyboardButton("📈 Trades", callback_data="trades"),
         InlineKeyboardButton("📉 Chart", callback_data="chart")],
        [InlineKeyboardButton("▶️ Start", callback_data="start"),
         InlineKeyboardButton("⏸ Stop", callback_data="stop")]
    ])

# =========================
# 📊 DASHBOARD
# =========================
def build_dashboard():
    if not bot_running:
        return "⏸ Bot Stopped"

    msg = "📊 LIVE DASHBOARD\n\n"
    total = 0

    for t, trade in active_trades.items():
        price = get_ltp(t)
        entry = trade["entry"]

        pnl = price - entry if trade["type"] == "BUY" else entry - price
        total += pnl

        msg += f"{t} | {trade['type']} | ₹{pnl:.2f}\n"

    msg += f"\n💰 Total: ₹{total:.2f}"
    return msg if active_trades else msg + "\n\nNo trades"

# =========================
# 📉 CHART
# =========================
def generate_chart(ticker):
    df = get_data(ticker)
    if df.empty:
        return None

    plt.figure(figsize=(8,4))
    plt.plot(df['Close'])
    plt.title(ticker)
    plt.grid(True)
    plt.tight_layout()

    file = f"{ticker}.png"
    plt.savefig(file)
    plt.close()
    return file

# =========================
# 🤖 TELEGRAM HANDLER
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Stock Bot", reply_markup=get_menu())

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running, dashboard_message_id, dashboard_chat_id

    q = update.callback_query
    await q.answer()

    if q.data == "dashboard":
        msg = build_dashboard()
        sent = await q.message.reply_text(msg, reply_markup=get_menu())
        dashboard_message_id = sent.message_id
        dashboard_chat_id = sent.chat_id

    elif q.data == "chart":
        if active_trades:
            ticker = list(active_trades.keys())[0]
            file = generate_chart(ticker)

            if file:
                with open(file, 'rb') as f:
                    await context.bot.send_photo(chat_id=q.message.chat_id, photo=f)
                os.remove(file)

# =========================
# 📊 STRATEGY
# =========================
stocks = ["RELIANCE.NS","TCS.NS","INFY.NS"]

def analyze(ticker):
    df = get_data(ticker)
    if df.empty or len(df) < 50:
        return

    close = df['Close']
    df['SMA20'] = ta.trend.sma_indicator(close, 20)

    price = float(close.iloc[-1])
    sma20 = float(df['SMA20'].iloc[-1])

    if ticker not in active_trades and price > sma20:
        active_trades[ticker] = {"type": "BUY", "entry": price}
        send_telegram(f"BUY {ticker} @ ₹{price:.2f}")

# =========================
# 🔁 LOOP
# =========================
def run_bot():
    while True:
        if is_market_open():
            for s in stocks:
                analyze(s)
        time.sleep(60)

# =========================
# 🤖 TELEGRAM RUN
# =========================
def run_telegram():
    import asyncio

    async def main():
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button))

        logging.info("Telegram started")
        await app.run_polling()

    asyncio.run(main())

# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()
    run_telegram()