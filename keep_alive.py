from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot Chứng Khoán Đang Chạy 24/7!"

def run():
    # Render mặc định dùng cổng này cho các ứng dụng web
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()