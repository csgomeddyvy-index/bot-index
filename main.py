import discord
from discord.ext import commands, tasks
import pandas as pd
from vnstock import Vnstock # Đã sửa thành vnstock chuẩn
import datetime
import pytz
import os
import google.generativeai as genai
from keep_alive import keep_alive 

# --- 1. LẤY BIẾN MÔI TRƯỜNG TỪ RENDER ---
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 2. CẤU HÌNH AI GEMINI ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. CẤU HÌNH BOT CÓ TÍNH NĂNG TƯƠNG TÁC LỆNH ---
intents = discord.Intents.default()
intents.message_content = True # Bắt buộc phải có để bot đọc được lệnh !soi
bot = commands.Bot(command_prefix='!', intents=intents)

danh_sach_ma = ['FPT', 'HPG', 'SSI', 'MWG', 'VND', 'VHM']

# ==========================================
# TÍNH NĂNG MỚI: TƯƠNG TÁC LỆNH !soi
# ==========================================
@bot.command(name='soi')
async def soi_cophieu(ctx, ma_cp: str):
    ma_cp = ma_cp.upper()
    await ctx.send(f"⏳ Đang thu thập dữ liệu và phân tích chuyên sâu mã **{ma_cp}**... Chờ xíu nhé!")
    
    try:
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.datetime.now(vn_tz)
        
        # Lấy dữ liệu 30 ngày
        stock = Vnstock().stock(symbol=ma_cp, source='TCBS')
        df = stock.quote.history(start=(now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), 
                                 end=now.strftime('%Y-%m-%d'))
        
        if df.empty:
            await ctx.send(f"❌ Không tìm thấy dữ liệu cho mã {ma_cp}. Bạn gõ đúng mã chưa?")
            return
            
        gia_hien_tai = df['close'].iloc[-1]
        khoi_luong = df['volume'].iloc[-1]
        gia_thap_nhat = df['low'].min()
        gia_cao_nhat = df['high'].max()
        
        # Prompt ép AI nói dài và chi tiết
        prompt = f"""
        Bạn là một chuyên gia phân tích chứng khoán Việt Nam lão luyện.
        Hãy phân tích THẬT CHI TIẾT và CHUYÊN SÂU mã cổ phiếu {ma_cp} dựa trên dữ liệu sau:
        - Giá hiện tại: {gia_hien_tai} VND
        - Khối lượng giao dịch: {khoi_luong:,.0f} cổ phiếu.
        - Biên độ giá 30 ngày qua: {gia_thap_nhat} - {gia_cao_nhat} VND.
        
        Vui lòng chia bài phân tích thành các phần rõ ràng:
        1. Vị thế giá: Đánh giá giá hiện tại so với lịch sử 30 ngày (Đang tích lũy, vượt đỉnh hay dò đáy?).
        2. Dòng tiền: Khối lượng hiện tại nói lên điều gì về tâm lý nhà đầu tư?
        3. Triển vọng ngành: Ngành của {ma_cp} có đang được hưởng lợi từ vĩ mô không?
        4. Hành động cụ thể: Lời khuyên Mua/Bán/Nắm giữ kèm theo điểm cắt lỗ/chốt lời dự kiến.
        """
        
        response = await model.generate_content_async(prompt)
        nhan_dinh_ai = response.text
        
        # Đóng gói tin nhắn
        msg = (f"📊 **BÁO CÁO PHÂN TÍCH MÃ: {ma_cp}** 📊\n"
               f"💰 Giá: **{gia_hien_tai}** | 📦 Vol: **{khoi_luong:,.0f}**\n"
               f"📉 Đáy 1 tháng: {gia_thap_nhat} | 📈 Đỉnh 1 tháng: {gia_cao_nhat}\n\n"
               f"🧠 **AI Phân Tích Chuyên Sâu:**\n"
               f"{nhan_dinh_ai}")
               
        # Chia nhỏ tin nhắn nếu quá dài (Luật của Discord)
        if len(msg) > 1900:
            chunks = [msg[i:i+1900] for i in range(0, len(msg), 1900)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(msg)
            
    except Exception as e:
        await ctx.send(f"❌ Có lỗi khi phân tích mã {ma_cp}: {e}")

# ==========================================
# TÍNH NĂNG CŨ: TỰ ĐỘNG SOÁT BẢNG ĐIỆN 5 PHÚT/LẦN
# ==========================================
@tasks.loop(minutes=5)
async def quet_bang_dien():
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(vn_tz)
    if now.weekday() >= 5: return
    
    thoi_gian_hien_tai = now.hour * 100 + now.minute
    trong_gio_sang = 900 <= thoi_gian_hien_tai <= 1130
    trong_gio_chieu = 1300 <= thoi_gian_hien_tai <= 1445
    
    if not (trong_gio_sang or trong_gio_chieu): return
    if CHANNEL_ID == 0: return
        
    channel = bot.get_channel(CHANNEL_ID)
    
    for ma in danh_sach_ma:
        try:
            stock = Vnstock().stock(symbol=ma, source='TCBS')
            df = stock.quote.history(start=(now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), end=now.strftime('%Y-%m-%d'))
            
            if not df.empty:
                gia_hien_tai = df['close'].iloc[-1]
                khoi_luong = df['volume'].iloc[-1]
                
                if khoi_luong > 2000000: 
                    # Prompt tự động cũng được yêu cầu chi tiết hơn
                    prompt = f"""
                    Cổ phiếu {ma} đang có khối lượng giao dịch đột biến ({khoi_luong:,.0f} cổ phiếu), giá hiện tại là {gia_hien_tai}.
                    Hãy phân tích thật chi tiết: Tại sao dòng tiền lại đột biến lúc này? Rủi ro và cơ hội là gì? Lời khuyên hành động tức thời?
                    """
                    response = await model.generate_content_async(prompt)
                    
                    msg = (f"🚨 **CẢNH BÁO VOL ĐỘT BIẾN: {ma}** 🚨\n"
                           f"💰 Giá: {gia_hien_tai} | 📊 Vol: {khoi_luong:,.0f}\n\n"
                           f"🧠 **Nhận định chi tiết:**\n{response.text}")
                           
                    if channel:
                        if len(msg) > 1900:
                            await channel.send(msg[:1900] + "...\n*(Nội dung quá dài đã được cắt bớt)*")
                        else:
                            await channel.send(msg)
        except Exception as e:
            print(f"Lỗi ở mã {ma}: {e}")

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} đã online và sẵn sàng nhận lệnh !soi')
    quet_bang_dien.start() 

if __name__ == "__main__":
    keep_alive()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Chưa cấu hình DISCORD_TOKEN")
