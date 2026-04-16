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

# =========================
# 🌐 FLASK SERVER (RENDER)
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
data_cache = {}

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
    elif now.time() < dt_time(9, 15):
        pass
    else:
        return

    sleep_seconds = (market_start - now).total_seconds()
    print(f"⏳ Sleeping {int(sleep_seconds/60)} mins")
    time.sleep(sleep_seconds)

# =========================
# 📲 TELEGRAM
# =========================
def send_telegram(msg):
    try:
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print("⚠️ Telegram not set")
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

# =========================
# 🧠 FUNDAMENTAL FILTER
# =========================
def is_good_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        pe = info.get("trailingPE")
        roe = info.get("returnOnEquity")

        return pe and roe and pe < 30 and roe > 0.12
    except:
        return False

# =========================
# 📊 DATA CACHE
# =========================
def get_data(ticker):
    try:
        now = time.time()

        if ticker in data_cache:
            last_time, df = data_cache[ticker]
            if now - last_time < 30:   # cache 30 sec
                return df

        df = yf.download(ticker, interval="5m", period="1d", progress=False)

        if not df.empty:
            data_cache[ticker] = (now, df)

        return df
    except:
        return pd.DataFrame()

# =========================
# 🚀 STOCK PICKER
# =========================
def get_active_stocks():
    base = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "SBIN.NS", "LT.NS", "ITC.NS"
    ]

    selected = []

    for t in base:
        df = get_data(t)
        if df.empty or len(df) < 30:
            continue

        price_change = (df['Close'].iloc[-1] - df['Close'].iloc[-5]) / df['Close'].iloc[-5] * 100
        vol = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]

        if abs(price_change) > 0.2 and vol > avg_vol:
            selected.append(t)

    return selected

# =========================
# 📊 ATR STOPLOSS
# =========================
def get_atr(df):
    high = df['High']
    low = df['Low']
    close = df['Close']
    return ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]

# =========================
# 📊 STRATEGY
# =========================
def analyze_stock(ticker):
    try:
        if ticker in cooldowns and time.time() - cooldowns[ticker] < 60:
            return

        if not is_good_stock(ticker):
            print(ticker, "❌ weak fundamentals")
            return

        df = get_data(ticker)
        if df.empty or len(df) < 50:
            return

        close = df['Close']

        df['RSI'] = ta.momentum.rsi(close, 14)
        df['VOL_AVG'] = df['Volume'].rolling(20).mean()
        df['HIGH_20'] = df['High'].rolling(20).max()
        df['LOW_20'] = df['Low'].rolling(20).min()

        price = float(close.iloc[-1])
        rsi = float(df['RSI'].iloc[-1])
        vol = float(df['Volume'].iloc[-1])
        vol_avg = float(df['VOL_AVG'].iloc[-1])
        prev_high = float(df['HIGH_20'].iloc[-2])
        prev_low = float(df['LOW_20'].iloc[-2])

        atr = get_atr(df)

        high_vol = vol > vol_avg

        signal = "HOLD"

        # 🔥 STRONGER FILTER
        if price > prev_high and high_vol and rsi > 55:
            signal = "BUY"
        elif price < prev_low and high_vol and rsi < 45:
            signal = "SELL"

        # =====================
        # 🚀 ENTRY
        # =====================
        if ticker not in active_trades:

            if signal == "BUY":
                active_trades[ticker] = {
                    "type": "BUY",
                    "sl": price - atr,
                    "tp": price + (2 * atr),
                    "highest": price
                }
                send_telegram(f"🚀 BUY {ticker} @ {price:.2f}")
                cooldowns[ticker] = time.time()

            elif signal == "SELL":
                active_trades[ticker] = {
                    "type": "SELL",
                    "sl": price + atr,
                    "tp": price - (2 * atr),
                    "lowest": price
                }
                send_telegram(f"🔻 SELL {ticker} @ {price:.2f}")
                cooldowns[ticker] = time.time()

        # =====================
        # 🔄 TRADE MANAGEMENT
        # =====================
        if ticker in active_trades:
            trade = active_trades[ticker]

            if trade["type"] == "BUY":
                if price > trade["highest"]:
                    trade["highest"] = price
                    trade["sl"] = price - atr * 0.8

                if price <= trade["sl"] or price >= trade["tp"]:
                    send_telegram(f"❌ EXIT BUY {ticker} @ {price:.2f}")
                    del active_trades[ticker]

            elif trade["type"] == "SELL":
                if price < trade["lowest"]:
                    trade["lowest"] = price
                    trade["sl"] = price + atr * 0.8

                if price >= trade["sl"] or price <= trade["tp"]:
                    send_telegram(f"❌ EXIT SELL {ticker} @ {price:.2f}")
                    del active_trades[ticker]

        print(f"{ticker} | {signal} | ₹{price:.2f} | RSI {rsi:.1f}")

    except Exception as e:
        print(ticker, "ERROR:", e)

# =========================
# 🔁 MAIN LOOP
# =========================
def run_bot():
    while True:
        try:
            if not is_market_open():
                sleep_until_market_open()

            print("\n🔄 Scanning market...\n")

            stocks = get_active_stocks()
            print("🔥 Active stocks:", stocks)

            for s in stocks:
                analyze_stock(s)

            time.sleep(60)

        except Exception as e:
            print("MAIN ERROR:", e)
            time.sleep(10)

# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    t1 = threading.Thread(target=run_web)
    t1.daemon = True
    t1.start()

    run_bot()