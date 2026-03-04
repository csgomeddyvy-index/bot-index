import discord
from discord.ext import tasks
import pandas as pd
from vnstock3 import Vnstock
import datetime
import os
from keep_alive import keep_alive # Import web server giả

# Lấy Token và ID từ môi trường của Render (Bảo mật tuyệt đối)
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

danh_sach_ma = ['FPT', 'HPG', 'SSI', 'MWG', 'VND']

@tasks.loop(minutes=5)
async def quet_bang_dien():
    # ... (Giữ nguyên đoạn code quét bảng điện của bạn ở trên) ...
    pass 

@client.event
async def on_ready():
    print(f'✅ Bot {client.user} đã online!')
    quet_bang_dien.start() 

# Bật web server giả lên trước
keep_alive()
# Sau đó chạy bot
client.run(TOKEN)