from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "✅ Server Bot Chứng Khoán Đang Hoạt Động 24/7!"

def run():
    # Render yêu cầu các Web Service phải mở port, mặc định dùng 8080 hoặc 10000
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()