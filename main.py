import discord
from discord.ext import tasks
import pandas as pd
from vnstock3 import Vnstock
import datetime
import pytz
import os
import google.generativeai as genai
from keep_alive import keep_alive # Nạp server giả vào

# --- 1. LẤY BIẾN MÔI TRƯỜNG TỪ RENDER ---
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 2. CẤU HÌNH AI GEMINI ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# Danh sách cổ phiếu muốn AI soi
danh_sach_ma = ['FPT', 'HPG', 'SSI', 'MWG', 'VND', 'VHM']

# --- 3. VÒNG LẶP SOÁT LỖI (5 PHÚT/LẦN) ---
@tasks.loop(minutes=5)
async def quet_bang_dien():
    # Lấy đúng giờ Việt Nam
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(vn_tz)
    
    # Nghỉ Thứ 7, Chủ Nhật
    if now.weekday() >= 5: 
        return
        
    # Lọc giờ giao dịch (9h-11h30 và 13h-14h45)
    thoi_gian_hien_tai = now.hour * 100 + now.minute
    trong_gio_sang = 900 <= thoi_gian_hien_tai <= 1130
    trong_gio_chieu = 1300 <= thoi_gian_hien_tai <= 1445
    
    if not (trong_gio_sang or trong_gio_chieu):
        return

    if CHANNEL_ID == 0:
        return
        
    channel = client.get_channel(CHANNEL_ID)
    
    for ma in danh_sach_ma:
        try:
            # Lấy dữ liệu 30 ngày gần nhất để xem xu hướng
            stock = Vnstock().stock(symbol=ma, source='TCBS')
            df = stock.quote.history(start=(now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), 
                                     end=now.strftime('%Y-%m-%d'))
            
            if not df.empty:
                gia_hien_tai = df['close'].iloc[-1]
                khoi_luong = df['volume'].iloc[-1]
                
                # Logic đột biến (sửa con số 2 triệu này tùy vào mã lớn hay nhỏ)
                if khoi_luong > 2000000: 
                    # Prompt mớm cho Gemini AI
                    prompt = f"""
                    Bạn là chuyên gia phân tích chứng khoán Việt Nam.
                    Nhận định cực kỳ ngắn gọn (dưới 80 chữ) về cổ phiếu {ma}:
                    - Giá hiện tại: {gia_hien_tai} VND
                    - Khối lượng: {khoi_luong} cổ phiếu (đang đột biến mạnh trong phiên).
                    Dòng tiền này có ý nghĩa gì? Có nên mua ngay không? Trả lời súc tích.
                    """
                    
                    response = await model.generate_content_async(prompt)
                    nhan_dinh_ai = response.text
                    
                    # Cấu trúc tin nhắn gửi lên Discord
                    msg = (f"🚨 **TÍN HIỆU ĐỘT BIẾN: {ma}** 🚨\n"
                           f"⏱ Thời gian: {now.strftime('%H:%M %d/%m/%Y')}\n"
                           f"💰 Giá: {gia_hien_tai} | 📊 Vol: {khoi_luong:,.0f}\n\n"
                           f"🧠 **AI Gemini Nhận định:**\n"
                           f"> {nhan_dinh_ai}\n"
                           f"----------------------------------")
                           
                    if channel:
                        await channel.send(msg)
                    
        except Exception as e:
            print(f"Lỗi ở mã {ma}: {e}")

@client.event
async def on_ready():
    print(f'✅ Bot {client.user} đã online!')
    quet_bang_dien.start() 

if __name__ == "__main__":
    # 1. Bật web server giả lên trước
    keep_alive()
    # 2. Chạy Bot Discord
    if TOKEN:
        client.run(TOKEN)
    else:
        print("❌ Chưa cấu hình DISCORD_TOKEN")