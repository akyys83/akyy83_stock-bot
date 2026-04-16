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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# =========================
# 🌐 FLASK SERVER
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Stock bot running 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================
# 🔑 ENV
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# 🧠 MEMORY
# =========================
active_trades = {}
cooldowns = {}
bot_running = True
ltp_cache = {}

# =========================
# 🕒 MARKET TIME
# =========================
def is_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    return dt_time(9, 15) <= now.time() <= dt_time(15, 30)

def sleep_until_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)

    if now.time() > dt_time(15, 30):
        market_start += timedelta(days=1)

    sleep_seconds = (market_start - now).total_seconds()
    time.sleep(max(sleep_seconds, 0))

# =========================
# 📲 TELEGRAM SEND
# =========================
def send_telegram(msg):
    try:
        if not TELEGRAM_TOKEN or not CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# =========================
# 📊 MENU
# =========================
def get_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("▶️ Start", callback_data="start")],
        [InlineKeyboardButton("⏸ Stop", callback_data="stop")],
        [InlineKeyboardButton("📈 Trades", callback_data="trades")],
        [InlineKeyboardButton("💰 PnL (Live)", callback_data="pnl")]
    ])

# =========================
# 🚀 TELEGRAM START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Stock Bot Dashboard", reply_markup=get_menu())

# =========================
# 💰 LTP CACHE
# =========================
def get_ltp(ticker):
    try:
        now = time.time()

        if ticker in ltp_cache:
            last_time, price = ltp_cache[ticker]
            if now - last_time < 5:
                return price

        df = yf.download(ticker, interval="1m", period="1d", progress=False)

        if not df.empty:
            price = float(df['Close'].iloc[-1])
            ltp_cache[ticker] = (now, price)
            return price

    except:
        pass

    return 0

# =========================
# 💰 LIVE PNL LOOP
# =========================
async def live_pnl(update, context):
    query = update.callback_query

    while True:
        msg = ""

        total = 0

        for t, trade in active_trades.items():
            price = get_ltp(t)
            entry = trade["entry"]

            pnl = price - entry if trade["type"] == "BUY" else entry - price

            total += pnl

            msg += f"{t}\nEntry: ₹{entry:.2f}\nLTP: ₹{price:.2f}\nPnL: ₹{pnl:.2f}\n\n"

        msg += f"💰 TOTAL: ₹{total:.2f}"

        try:
            await query.edit_message_text(msg, reply_markup=get_menu())
            await asyncio.sleep(5)
        except:
            break

# =========================
# 🔘 BUTTON HANDLER
# =========================
import asyncio

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running

    q = update.callback_query
    await q.answer()

    if q.data == "status":
        msg = "🟢 Running" if bot_running else "🔴 Stopped"
        await q.edit_message_text(msg, reply_markup=get_menu())

    elif q.data == "start":
        bot_running = True
        await q.edit_message_text("▶️ Started", reply_markup=get_menu())

    elif q.data == "stop":
        bot_running = False
        await q.edit_message_text("⏸ Stopped", reply_markup=get_menu())

    elif q.data == "trades":
        if not active_trades:
            msg = "No trades"
        else:
            msg = "\n".join([f"{k}: {v['type']}" for k,v in active_trades.items()])
        await q.edit_message_text(msg, reply_markup=get_menu())

    elif q.data == "pnl":
        await live_pnl(update, context)

# =========================
# 🤖 TELEGRAM RUN
# =========================
def run_telegram():
    try:
        bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        bot.add_handler(CommandHandler("start", start))
        bot.add_handler(CallbackQueryHandler(button))

        print("Telegram started")

        bot.run_polling()

    except Exception as e:
        print("Telegram error:", e)

# =========================
# 📊 DATA
# =========================
def get_data(ticker):
    try:
        return yf.download(ticker, interval="5m", period="1d", progress=False)
    except:
        return pd.DataFrame()

# =========================
# 🚀 STOCK LIST
# =========================
stocks = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS",
    "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "ITC.NS"
]

# =========================
# 📊 STRATEGY
# =========================
def analyze(ticker):
    try:
        if ticker in cooldowns and time.time() - cooldowns[ticker] < 120:
            return

        df = get_data(ticker)
        if df.empty or len(df) < 50:
            return

        close = df['Close']

        df['RSI'] = ta.momentum.rsi(close, 14)
        df['SMA20'] = ta.trend.sma_indicator(close, 20)
        df['SMA50'] = ta.trend.sma_indicator(close, 50)

        price = float(close.iloc[-1])
        rsi = float(df['RSI'].iloc[-1])
        sma20 = float(df['SMA20'].iloc[-1])
        sma50 = float(df['SMA50'].iloc[-1])

        signal = None

        if price > sma20 and sma20 > sma50 and rsi > 50:
            signal = "BUY"
        elif price < sma20 and sma20 < sma50 and rsi < 50:
            signal = "SELL"

        if ticker not in active_trades and signal:
            active_trades[ticker] = {"type": signal, "entry": price}
            send_telegram(f"{signal} {ticker} @ ₹{price:.2f}")
            cooldowns[ticker] = time.time()

        if ticker in active_trades:
            trade = active_trades[ticker]

            if trade["type"] == "BUY" and price < sma20:
                send_telegram(f"EXIT BUY {ticker} @ ₹{price:.2f}")
                del active_trades[ticker]

            elif trade["type"] == "SELL" and price > sma20:
                send_telegram(f"EXIT SELL {ticker} @ ₹{price:.2f}")
                del active_trades[ticker]

    except Exception as e:
        print("Error:", ticker, e)

# =========================
# 🔁 BOT LOOP
# =========================
def run_bot():
    global bot_running

    while True:
        try:
            if not bot_running:
                time.sleep(5)
                continue

            if not is_market_open():
                sleep_until_market_open()

            print("Scanning...")

            for s in stocks:
                analyze(s)

            time.sleep(60)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(10)

# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=run_telegram, daemon=True).start()
    run_bot()