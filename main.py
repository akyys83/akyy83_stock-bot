import yfinance as yf
import pandas as pd
import ta
import time
import requests
from datetime import datetime, time as dt_time, timedelta
import pytz

# 🔑 ADD YOUR DETAILS
TELEGRAM_TOKEN = "8331695862:AAGoGIVDY95PncAZXswx3HRcVRrOfRBVR8g"
CHAT_ID = "6368208787"

last_signals = {}
active_trades = {}

# 🕒 MARKET TIME (IST)
def is_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    market_start = dt_time(9, 15)
    market_end = dt_time(15, 30)

    return market_start <= now.time() <= market_end


def sleep_until_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    market_start_today = now.replace(hour=9, minute=15, second=0, microsecond=0)

    if now.time() > dt_time(15, 30):
        next_open = market_start_today + timedelta(days=1)
    elif now.time() < dt_time(9, 15):
        next_open = market_start_today
    else:
        return

    sleep_seconds = (next_open - now).total_seconds()

    print("⏳ Sleeping until 9:15 AM IST...")
    time.sleep(sleep_seconds)


# 📲 TELEGRAM
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram Error:", e)


# 🧠 FUNDAMENTAL FILTER
def is_good_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        pe = info.get("trailingPE", None)
        roe = info.get("returnOnEquity", None)
        debt = info.get("debtToEquity", None)

        # Simple safety rules
        if pe and pe < 30 and roe and roe > 0.15:
            return True

    except:
        pass

    return False


# 🚀 AUTO STOCK PICKER
def get_active_stocks():
    base_stocks = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "SBIN.NS", "LT.NS", "ITC.NS"
    ]

    selected = []

    for stock in base_stocks:
        try:
            df = yf.download(stock, interval="5m", period="1d")

            if df.empty:
                continue

            price_change = df['Close'].iloc[-1] - df['Close'].iloc[-5]
            volume = df['Volume'].iloc[-1]
            avg_volume = df['Volume'].rolling(20).mean().iloc[-1]

            if abs(price_change) > 2 and volume > avg_volume:
                selected.append(stock)

        except:
            continue

    return selected


# 📊 STRATEGY
def analyze_stock(ticker):
    try:
        # 🔴 Skip weak companies
        if not is_good_stock(ticker):
            print(f"{ticker} ❌ Weak fundamentals - Skipped")
            return

        df = yf.download(ticker, interval="5m", period="1d")

        if df.empty:
            return

        close = df['Close'].squeeze()
        volume = df['Volume'].squeeze()

        df['SMA_20'] = ta.trend.sma_indicator(close, 20)
        df['SMA_50'] = ta.trend.sma_indicator(close, 50)
        df['RSI'] = ta.momentum.rsi(close, 14)
        df['VOL_AVG'] = volume.rolling(20).mean()

        df['HIGH_20'] = df['High'].rolling(20).max()
        df['LOW_20'] = df['Low'].rolling(20).min()

        price = df['Close'].iloc[-1].item()
        rsi = df['RSI'].iloc[-1].item()
        vol = df['Volume'].iloc[-1].item()
        vol_avg = df['VOL_AVG'].iloc[-1].item()
        prev_high = df['HIGH_20'].iloc[-2].item()
        prev_low = df['LOW_20'].iloc[-2].item()

        high_volume = vol > vol_avg

        # 🎯 SIGNAL
        if price > prev_high and high_volume:
            signal = "BUY"
        elif price < prev_low and high_volume:
            signal = "SELL"
        else:
            signal = "HOLD"

        # 🚀 ENTRY
        if ticker not in active_trades:

            if signal == "BUY":
                active_trades[ticker] = {
                    "type": "BUY",
                    "sl": price - 10,
                    "highest": price
                }
                send_telegram(f"🚨 BUY {ticker} @ {price:.2f}")

            elif signal == "SELL":
                active_trades[ticker] = {
                    "type": "SELL",
                    "sl": price + 10,
                    "lowest": price
                }
                send_telegram(f"🚨 SELL {ticker} @ {price:.2f}")

        # 🔄 TRAILING
        if ticker in active_trades:
            trade = active_trades[ticker]

            if trade["type"] == "BUY":
                if price > trade["highest"]:
                    trade["highest"] = price
                    trade["sl"] = price - 5

                if price <= trade["sl"]:
                    send_telegram(f"❌ EXIT BUY {ticker} @ {price:.2f}")
                    del active_trades[ticker]

            elif trade["type"] == "SELL":
                if price < trade["lowest"]:
                    trade["lowest"] = price
                    trade["sl"] = price + 5

                if price >= trade["sl"]:
                    send_telegram(f"❌ EXIT SELL {ticker} @ {price:.2f}")
                    del active_trades[ticker]

        print(f"{ticker} | {signal} | Price: {price:.2f}")

    except Exception as e:
        print("Error:", e)


# 🔁 MAIN LOOP
while True:

    if not is_market_open():
        sleep_until_market_open()

    print("\n🔄 Scanning...\n")

    stocks = get_active_stocks()
    print("🔥 Active:", stocks)

    for stock in stocks:
        analyze_stock(stock)

    time.sleep(60)