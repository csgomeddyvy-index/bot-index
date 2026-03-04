import discord
from discord.ext import commands, tasks
import pandas as pd
from vnstock import Vnstock
import datetime
import pytz
import os
import io
import asyncio
import google.generativeai as genai
import mplfinance as mpf
from keep_alive import keep_alive 

# --- 1. LẤY BIẾN MÔI TRƯỜNG ---
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Ép hệ thống nhận diện API Key của vnstock
VNSTOCK_API_KEY = os.environ.get("VNSTOCK_API_KEY")
if VNSTOCK_API_KEY:
    os.environ['VNSTOCK_API_KEY'] = VNSTOCK_API_KEY

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

danh_sach_ma = ['FPT', 'HPG', 'SSI', 'MWG', 'VND', 'VHM']

# ==========================================
# LỆNH !soi: CÓ VẼ BIỂU ĐỒ NẾN + AI
# ==========================================
@bot.command(name='soi')
async def soi_cophieu(ctx, ma_cp: str):
    ma_cp = ma_cp.upper()
    message = await ctx.send(f"⏳ Đang tải dữ liệu và vẽ biểu đồ mã **{ma_cp}**... Chờ xíu nhé!")
    
    try:
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.datetime.now(vn_tz)
        
        # Bọc lỗi cho phần gọi vnstock
        try:
            stock = Vnstock().stock(symbol=ma_cp, source='TCBS')
            df = stock.quote.history(start=(now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), end=now.strftime('%Y-%m-%d'))
        except Exception as api_err:
            await message.edit(content=f"❌ Không thể tải dữ liệu từ máy chủ chứng khoán lúc này. Lỗi: {api_err}")
            return
        
        if df is None or df.empty:
            await message.edit(content=f"❌ Không tìm thấy dữ liệu cho mã {ma_cp}. Bạn gõ đúng mã chưa?")
            return
            
        gia_hien_tai = df['close'].iloc[-1]
        khoi_luong = df['volume'].iloc[-1]
        gia_thap_nhat = df['low'].min()
        gia_cao_nhat = df['high'].max()

        df_chart = df.copy()
        if 'time' in df_chart.columns:
            df_chart['time'] = pd.to_datetime(df_chart['time'])
            df_chart.set_index('time', inplace=True)
            
        df_chart.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        
        buf = io.BytesIO()
        mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridaxis='both', gridstyle=':')
        
        mpf.plot(df_chart, type='candle', volume=True, style=s, 
                 title=f"\nBieu do {ma_cp} (30 Ngay)", 
                 ylabel="Gia", ylabel_lower="Khoi Luong",
                 savefig=dict(fname=buf, dpi=100, bbox_inches='tight'))
        buf.seek(0)
        
        chart_file = discord.File(fp=buf, filename=f"{ma_cp}_chart.png")

        prompt = f"""
        Chuyên gia chứng khoán phân tích mã {ma_cp}:
        - Giá: {gia_hien_tai}
        - Khối lượng: {khoi_luong:,.0f}
        - Biên độ 30 ngày: {gia_thap_nhat} - {gia_cao_nhat}.
        Chia thành: 1. Vị thế giá 2. Dòng tiền 3. Hành động (Mua/Bán/Cắt lỗ).
        """
        response = await model.generate_content_async(prompt)
        nhan_dinh_ai = response.text
        
        msg = (f"📊 **BÁO CÁO MÃ: {ma_cp}** 📊\n"
               f"💰 Giá: **{gia_hien_tai}** | 📦 Vol: **{khoi_luong:,.0f}**\n\n"
               f"🧠 **AI Nhận Định:**\n"
               f"{nhan_dinh_ai}")
               
        await message.delete()
        await ctx.send(content=msg[:1900], file=chart_file)
            
    except Exception as e:
        await message.edit(content=f"❌ Có lỗi bất ngờ xảy ra khi xử lý: {e}")

# ==========================================
# SOÁT BẢNG ĐIỆN TỰ ĐỘNG
# ==========================================
@tasks.loop(minutes=5)
async def quet_bang_dien():
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(vn_tz)
    if now.weekday() >= 5: return
    
    thoi_gian_hien_tai = now.hour * 100 + now.minute
    if not ((900 <= thoi_gian_hien_tai <= 1130) or (1300 <= thoi_gian_hien_tai <= 1445)): return
    if CHANNEL_ID == 0: return
        
    channel = bot.get_channel(CHANNEL_ID)
    
    for ma in danh_sach_ma:
        try:
            stock = Vnstock().stock(symbol=ma, source='TCBS')
            df = stock.quote.history(start=(now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), end=now.strftime('%Y-%m-%d'))
            
            if df is not None and not df.empty:
                gia_hien_tai = df['close'].iloc[-1]
                khoi_luong = df['volume'].iloc[-1]
                
                if khoi_luong > 2000000: 
                    prompt = f"Mã {ma} có Vol đột biến {khoi_luong:,.0f}, giá {gia_hien_tai}. Phân tích ngắn gọn lý do và hành động."
                    response = await model.generate_content_async(prompt)
                    
                    msg = (f"🚨 **VOL ĐỘT BIẾN: {ma}** 🚨\n"
                           f"💰 Giá: {gia_hien_tai} | 📊 Vol: {khoi_luong:,.0f}\n\n"
                           f"🧠 **AI:**\n{response.text}")
                    if channel:
                        await channel.send(msg[:1900])
        except Exception as e:
            print(f"Lỗi ở mã {ma}: {e}")
        finally:
            # NHỊP THỞ QUAN TRỌNG: Bắt buộc nghỉ 3 giây trước khi quét mã tiếp theo
            await asyncio.sleep(3)

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} đã online vững vàng!')
    quet_bang_dien.start() 

if __name__ == "__main__":
    keep_alive()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Chưa cấu hình DISCORD_TOKEN")

