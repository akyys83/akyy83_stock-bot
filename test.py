import requests

TOKEN = "-:"
CHAT_ID = "-"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

data = {
    "chat_id": CHAT_ID,
    "text": "🔥 FINAL TEST"
}

response = requests.post(url, data=data)
print(response.text)
