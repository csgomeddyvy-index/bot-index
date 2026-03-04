import discord
from discord.ext import commands, tasks
import pandas as pd
import datetime
import pytz
import os
import io
import asyncio
import requests
import google.generativeai as genai
import mplfinance as mpf
from keep_alive import keep_alive 

# --- 1. LẤY BIẾN MÔI TRƯỜNG ---
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

danh_sach_ma = ['FPT', 'HPG', 'SSI', 'MWG', 'VND', 'VHM']

# ==========================================
# HÀM MỚI: GỌI TRỰC TIẾP API VNDIRECT (BAO TRÂU, KHÔNG CHẶN)
# ==========================================
def get_stock_data(ticker, days=30):
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(vn_tz)
    end_date = now.strftime('%Y-%m-%d')
    start_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    
    # API công khai của VNDirect lấy lịch sử giá
    url = f"https://finfo-api.vndirect.com.vn/v4/stock_prices?sort=date&q=code:{ticker}~date:gte:{start_date}~date:lte:{end_date}&size=100"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get('data', [])
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        # Sắp xếp và đổi tên cột chuẩn cho mplfinance
        df['time'] = pd.to_datetime(df['date'])
        df.set_index('time', inplace=True)
        # nmVolume là khối lượng khớp lệnh
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'nmVolume': 'Volume'}, inplace=True)
        
        # Ép kiểu dữ liệu về dạng số để vẽ biểu đồ không bị lỗi
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df.sort_index(inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    else:
        raise Exception(f"Lỗi truy cập VNDirect! Mã lỗi: {response.status_code}")

# ==========================================
# LỆNH !soi: CÓ VẼ BIỂU ĐỒ NẾN + AI
# ==========================================
@bot.command(name='soi')
async def soi_cophieu(ctx, ma_cp: str):
    ma_cp = ma_cp.upper()
    message = await ctx.send(f"⏳ Đang kéo dữ liệu từ VNDirect và phân tích mã **{ma_cp}**...")
    
    try:
        # Gọi API mới
        try:
            df = get_stock_data(ma_cp, days=30)
        except Exception as api_err:
            await message.edit(content=f"❌ Lỗi máy chủ chứng khoán: {api_err}")
            return
        
        if df.empty:
            await message.edit(content=f"❌ Không tìm thấy dữ liệu cho mã {ma_cp}.")
            return
            
        gia_hien_tai = df['Close'].iloc[-1]
        khoi_luong = df['Volume'].iloc[-1]
        gia_thap_nhat = df['Low'].min()
        gia_cao_nhat = df['High'].max()
        
        # Vẽ biểu đồ
        buf = io.BytesIO()
        mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridaxis='both', gridstyle=':')
        
        mpf.plot(df, type='candle', volume=True, style=s, 
                 title=f"\nBieu do {ma_cp} (30 Ngay)", 
                 ylabel="Gia", ylabel_lower="Khoi Luong",
                 savefig=dict(fname=buf, dpi=100, bbox_inches='tight'))
        buf.seek(0)
        chart_file = discord.File(fp=buf, filename=f"{ma_cp}_chart.png")

        # Hỏi AI Gemini
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
               f"💰 Giá: **{gia_hien_tai:,.0f}** | 📦 Vol: **{khoi_luong:,.0f}**\n\n"
               f"🧠 **AI Nhận Định:**\n"
               f"{nhan_dinh_ai}")
               
        await message.delete()
        await ctx.send(content=msg[:1900], file=chart_file)
            
    except Exception as e:
        await message.edit(content=f"❌ Có lỗi: {e}")

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
            df = get_stock_data(ma, days=5) 
            
            if not df.empty:
                gia_hien_tai = df['Close'].iloc[-1]
                khoi_luong = df['Volume'].iloc[-1]
                
                if khoi_luong > 2000000: 
                    prompt = f"Mã {ma} có Vol đột biến {khoi_luong:,.0f}, giá {gia_hien_tai}. Phân tích lý do và hành động."
                    response = await model.generate_content_async(prompt)
                    
                    msg = (f"🚨 **VOL ĐỘT BIẾN: {ma}** 🚨\n"
                           f"💰 Giá: {gia_hien_tai:,.0f} | 📊 Vol: {khoi_luong:,.0f}\n\n"
                           f"🧠 **AI:**\n{response.text}")
                    if channel:
                        await channel.send(msg[:1900])
        except Exception as e:
            print(f"Lỗi ở mã {ma}: {e}")
        finally:
            await asyncio.sleep(2) 

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} đã online! (Sử dụng API VNDirect)')
    quet_bang_dien.start() 

if __name__ == "__main__":
    keep_alive()
    if TOKEN:
        bot.run(TOKEN)
