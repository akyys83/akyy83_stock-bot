import requests

TOKEN = "8331695862:AAGoGIVDY95PncAZXswx3HRcVRrOfRBVR8g"
CHAT_ID = "6368208787"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

data = {
    "chat_id": CHAT_ID,
    "text": "🔥 FINAL TEST"
}

response = requests.post(url, data=data)
print(response.text)
