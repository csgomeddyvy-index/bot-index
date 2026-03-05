import discord
from discord.ext import commands, tasks
import pandas as pd
import datetime
import pytz
import os
import io
import asyncio
import requests
import time
import mplfinance as mpf
import feedparser 
from bs4 import BeautifulSoup 
import re 
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- 1. LẤY BIẾN TỪ FILE .env ---
load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 2. DANH SÁCH RỔ VN30 & BIẾN TOÀN CỤC ---
danh_sach_ma = [
    'ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 
    'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 
    'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE'
]

muc_canh_bao_vol = {ma: 0 for ma in danh_sach_ma}
ngay_giao_dich_hien_tai = None
bot_vua_khoi_dong = True
da_dang_tin = [] 
bot_vua_khoi_dong_tin_tuc = True

# ==========================================
# WEB SERVER NGẦM CHỐNG SLEEP CHO RENDER
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot Chứng Khoán VN30 đang hoạt động 24/7 trên Render!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# ==========================================
# HÀM LẤY DỮ LIỆU & TÍNH TOÁN CHỈ BÁO KỸ THUẬT
# ==========================================
def get_stock_data(ticker, days=30):
    end_time = int(time.time())
    start_time = end_time - ((days + 60) * 24 * 60 * 60) 
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={start_time}&to={end_time}&resolution=1&symbol={ticker}&type=stock"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if not data.get('t'): return pd.DataFrame()
            
            df = pd.DataFrame({
                'time': pd.to_datetime(data['t'], unit='s'),
                'Open': data['o'], 'High': data['h'], 'Low': data['l'], 'Close': data['c'], 'Volume': data['v']
            })
            df.set_index('time', inplace=True)
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
            
            df_daily = df.resample('D').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
            df_daily['MA10'] = df_daily['Close'].rolling(window=10).mean()
            df_daily['MA20'] = df_daily['Close'].rolling(window=20).mean()
            
            delta = df_daily['Close'].diff()
            gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            df_daily['RSI'] = 100 - (100 / (1 + rs))
            
            exp1 = df_daily['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df_daily['Close'].ewm(span=26, adjust=False).mean()
            df_daily['MACD'] = exp1 - exp2
            df_daily['Signal'] = df_daily['MACD'].ewm(span=9, adjust=False).mean()
            df_daily['Histogram'] = df_daily['MACD'] - df_daily['Signal']
            
            return df_daily.tail(days)
    except: pass
    return pd.DataFrame()

# ==========================================
# THUẬT TOÁN HỘI ĐỒNG: CHỐT 1 LỆNH DUY NHẤT
# ==========================================
def phan_tich_hanh_dong(gia, mo, tran, san, tham_chieu, vol, vol_tb, rsi, macd, signal):
    ty_le_vol = (vol / vol_tb) * 100 if vol_tb > 0 else 0
    loi_khuyen = ""
    
    if gia > tham_chieu:
        if rsi >= 70:
            loi_khuyen = f"⚠️ **GIỮ HÀNG / CHỜ CHỐT LỜI:** Tiền lớn đang đẩy (Vol {ty_le_vol:.0f}%, MACD đẹp) nhưng RSI đã chạm mốc {rsi:.1f} (Quá Mua). Tuyệt đối KHÔNG FOMO mua đuổi!"
        elif macd > signal:
            loi_khuyen = f"🟢 **MUA / GIA TĂNG:** Điểm mua VÀNG! Tiền lớn nổ (Vol {ty_le_vol:.0f}%), MACD cắt lên và RSI ({rsi:.1f}) còn dư địa an toàn."
        else:
            loi_khuyen = f"🟡 **MUA THĂM DÒ:** Tiền đang vào (Vol {ty_le_vol:.0f}%) nhưng MACD chưa đồng thuận tăng dứt khoát."
            
    elif gia < tham_chieu:
        if rsi <= 30:
            loi_khuyen = f"🎯 **QUAN SÁT TẠO ĐÁY:** Đang bị xả (Vol {ty_le_vol:.0f}%) nhưng RSI rớt về {rsi:.1f} (Vùng Quá Bán). Tuyệt đối NGỪNG BÁN THÁO!"
        elif macd < signal:
            loi_khuyen = f"🔴 **CẮT LỖ / BÁN DỨT KHOÁT:** Lực xả mạnh (Vol {ty_le_vol:.0f}%), MACD cắt xuống báo hiệu gãy trend. Bán phòng thủ ngay!"
        else:
            loi_khuyen = f"🟠 **HẠ TỶ TRỌNG:** Áp lực bán gia tăng, MACD suy yếu dần. Chủ động chốt lời bảo vệ vốn."
            
    else:
        loi_khuyen = "⚪ **ĐỨNG NGOÀI:** Giá đi ngang giằng co, chưa phân thắng bại."
        
    if gia >= tran: loi_khuyen = f"🔥 **DƯ MUA TRẦN:** Bùng nổ tuyệt đối! Gồng lãi tối đa."
    elif gia <= san: loi_khuyen = f"💀 **LAU SÀN:** Áp lực tháo chạy kinh hoàng. Cắt bằng mọi giá!"
        
    return loi_khuyen

# ==========================================
# QUÉT TIN TỨC CHỨNG KHOÁN (CHỈ LẤY TIN MỚI)
# ==========================================
@tasks.loop(minutes=10)
async def quet_tin_tuc():
    global da_dang_tin, bot_vua_khoi_dong_tin_tuc
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return
    try:
        feed = feedparser.parse("https://vnexpress.net/rss/kinh-doanh.rss")
        if not feed.entries: return
        
        # Nạp trí nhớ im lặng ở lần chạy đầu tiên
        if bot_vua_khoi_dong_tin_tuc:
            for entry in feed.entries[:15]:
                da_dang_tin.append(entry.link)
            bot_vua_khoi_dong_tin_tuc = False
            return
            
        for entry in feed.entries[:15]: 
            if entry.link in da_dang_tin: continue 
            da_dang_tin.append(entry.link)
            
            tieu_de = entry.title.upper()
            noi_dung = entry.description.upper()
            
            ma_lien_quan = [ma for ma in danh_sach_ma if re.search(rf'\b{ma}\b', tieu_de) or re.search(rf'\b{ma}\b', noi_dung)]
            tu_khoa_vimo = ["VN-INDEX", "LÃI SUẤT", "FED", "TỰ DOANH", "KHỐI NGOẠI", "CHỨNG KHOÁN"]
            is_vimo = any(tk in tieu_de for tk in tu_khoa_vimo)

            if ma_lien_quan or is_vimo:
                soup = BeautifulSoup(entry.description, 'html.parser')
                img_tag = soup.find('img')
                thumb = img_tag['src'] if img_tag else None
                noi_dung_sach = soup.get_text().strip()
                
                embed = discord.Embed(
                    title=f"📰 {entry.title}",
                    url=entry.link,
                    description=f"📍 **Từ khóa:** {', '.join(ma_lien_quan) if ma_lien_quan else 'Vĩ mô'}\n\n{noi_dung_sach[:180]}...",
                    color=0x3498db,
                    timestamp=datetime.datetime.now()
                )
                if thumb: embed.set_thumbnail(url=thumb)
                embed.set_footer(text="Nguồn: VNExpress | Auto News Update")
                await channel.send(embed=embed)
                
        if len(da_dang_tin) > 100: da_dang_tin = da_dang_tin[-50:]
    except Exception as e: print(f"Lỗi quét tin: {e}")

# ==========================================
# LỆNH !tinmoi (XEM BÀI BÁO MỚI NHẤT THỦ CÔNG)
# ==========================================
@bot.command(name='tinmoi')
async def tin_moi_nhat(ctx):
    msg_wait = await ctx.send("⏳ Đang đi lấy tờ báo mới nhất trên VNExpress về...")
    try:
        feed = feedparser.parse("https://vnexpress.net/rss/kinh-doanh.rss")
        if not feed.entries:
            await msg_wait.edit(content="❌ Hiện không lấy được tin tức nào, bạn thử lại sau nhé.")
            return
            
        entry = feed.entries[0]
        
        soup = BeautifulSoup(entry.description, 'html.parser')
        img_tag = soup.find('img')
        thumb = img_tag['src'] if img_tag else None
        noi_dung_sach = soup.get_text().strip()
        
        embed = discord.Embed(
            title=f"🔥 [TIN NÓNG MỚI NHẤT] {entry.title}",
            url=entry.link,
            description=f"{noi_dung_sach[:250]}...\n\n👉 **[Nhấn vào đây để đọc chi tiết]({entry.link})**",
            color=0xe74c3c, 
            timestamp=datetime.datetime.now()
        )
        if thumb: embed.set_thumbnail(url=thumb)
        embed.set_footer(text="Nguồn: VNExpress | Kích hoạt bằng lệnh !tinmoi")
        
        await msg_wait.delete()
        await ctx.send(embed=embed)
    except Exception as e: 
        await msg_wait.edit(content=f"❌ Có lỗi khi lấy tin: {e}")

# ==========================================
# LỆNH !soi (XEM BIỂU ĐỒ THỦ CÔNG)
# ==========================================
@bot.command(name='soi')
async def soi_cophieu(ctx, ma_cp: str):
    ma_cp = ma_cp.upper()
    msg_wait = await ctx.send(f"⏳ Đang load combo chỉ báo kỹ thuật mã **{ma_cp}**...")
    try:
        df = get_stock_data(ma_cp, days=30)
        if df.empty:
            await msg_wait.edit(content=f"❌ Không tìm thấy dữ liệu cho mã {ma_cp}."); return
            
        gia, mo, cao, thap, vol = df['Close'].iloc[-1], df['Open'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1], df['Volume'].iloc[-1]
        vol_tb = df['Volume'].iloc[:-1].mean()
        rsi = df['RSI'].iloc[-1]
        macd = df['MACD'].iloc[-1]
        signal = df['Signal'].iloc[-1]
        tham_chieu = df['Close'].iloc[-2]
        tran, san = tham_chieu * 1.07, tham_chieu * 0.93
        
        loi_khuyen = phan_tich_hanh_dong(gia, mo, tran, san, tham_chieu, vol, vol_tb, rsi, macd, signal)
        
        ap = [
            mpf.make_addplot(df['MA10'], color='blue', width=1.5),
            mpf.make_addplot(df['MA20'], color='orange', width=1.5),
            mpf.make_addplot(df['MACD'], panel=2, color='purple', ylabel='MACD'),
            mpf.make_addplot(df['Signal'], panel=2, color='orange'),
            mpf.make_addplot(df['Histogram'], type='bar', panel=2, color='gray', alpha=0.5)
        ]
        
        buf = io.BytesIO()
        mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridaxis='both', gridstyle=':')
        mpf.plot(df, type='candle', volume=True, addplot=ap, style=s, figratio=(10, 8), savefig=dict(fname=buf, dpi=100, bbox_inches='tight'))
        buf.seek(0)
        
        now = datetime.datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S %d/%m/%Y')
        report = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ **Cập nhật:** {now}\n"
            f"📊 **BẢNG ĐIỆN CHI TIẾT: {ma_cp}**\n\n"
            f"💎 **Giá Hiện Tại: `{gia:,.2f}`**\n"
            f"🟣 Trần: `{tran:,.2f}`  |  🔵 Sàn: `{san:,.2f}`  |  🟡 TC: `{tham_chieu:,.2f}`\n"
            f"🟢 Cao: `{cao:,.2f}`  |  🔴 Thấp: `{thap:,.2f}`  |  ⚪ Mở: `{mo:,.2f}`\n\n"
            f"📦 **Khối lượng:** `{vol:,.0f}` CP\n"
            f"📈 **Sức mạnh Vol:** `{ (vol/vol_tb)*100 if vol_tb > 0 else 0 :.1f}%` (So với TB)\n"
            f"⚡ **Chỉ báo RSI:** `{rsi:.1f}` | 💠 **MACD:** `{macd:.2f}`\n\n"
            f"🤖 **KHUYẾN NGHỊ KỸ THUẬT:**\n"
            f"👉 {loi_khuyen}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await msg_wait.delete()
        await ctx.send(content=report, file=discord.File(fp=buf, filename=f"{ma_cp}.png"))
    except Exception as e: await msg_wait.edit(content=f"❌ Lỗi: {e}")

# ==========================================
# QUÉT TỰ ĐỘNG BẢNG ĐIỆN (2 PHÚT/LẦN)
# ==========================================
@tasks.loop(minutes=2)
async def quet_bang_dien():
    global ngay_giao_dich_hien_tai, muc_canh_bao_vol, bot_vua_khoi_dong
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(vn_tz)
    
    if ngay_giao_dich_hien_tai != now.date():
        ngay_giao_dich_hien_tai, muc_canh_bao_vol, bot_vua_khoi_dong = now.date(), {ma: 0 for ma in danh_sach_ma}, True 
        
    if now.weekday() >= 5: return
    t = now.hour * 100 + now.minute
    if not ((900 <= t <= 1130) or (1300 <= t <= 1445)): return
    
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return
    
    for ma in danh_sach_ma:
        try:
            df = get_stock_data(ma, days=30)
            if not df.empty:
                gia, tham_chieu, mo, vol = df['Close'].iloc[-1], df['Close'].iloc[-2], df['Open'].iloc[-1], df['Volume'].iloc[-1]
                vol_tb = df['Volume'].iloc[:-1].mean()
                rsi = df['RSI'].iloc[-1]
                macd = df['MACD'].iloc[-1]
                signal = df['Signal'].iloc[-1]
                
                muc_hien_tai = int(vol // vol_tb) if vol_tb > 0 else 0
                if bot_vua_khoi_dong:
                    muc_canh_bao_vol[ma] = muc_hien_tai
                    continue
                    
                if muc_hien_tai > muc_canh_bao_vol.get(ma, 0) and muc_hien_tai >= 1:
                    muc_canh_bao_vol[ma] = muc_hien_tai
                    loi_khuyen = phan_tich_hanh_dong(gia, mo, tham_chieu*1.07, tham_chieu*0.93, tham_chieu, vol, vol_tb, rsi, macd, signal)
                    
                    ap = [
                        mpf.make_addplot(df['MA10'], color='blue', width=1),
                        mpf.make_addplot(df['MA20'], color='orange', width=1),
                        mpf.make_addplot(df['MACD'], panel=2, color='purple', ylabel='MACD'),
                        mpf.make_addplot(df['Signal'], panel=2, color='orange'),
                        mpf.make_addplot(df['Histogram'], type='bar', panel=2, color='gray', alpha=0.5)
                    ]
                    buf = io.BytesIO()
                    mpf.plot(df, type='candle', volume=True, addplot=ap, style='charles', figratio=(10, 8), savefig=dict(fname=buf, dpi=80))
                    buf.seek(0)
                    
                    msg = (
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚨 **BÁO ĐỘNG VOL ĐỘT BIẾN: {ma}** ({now.strftime('%H:%M:%S')})\n"
                        f"💰 **Giá:** `{gia:,.2f}` ({'🟢' if gia > tham_chieu else '🔴'})\n"
                        f"📦 **Vol bùng nổ:** `{vol:,.0f}` CP (Gấp `{vol/vol_tb:.1f}` lần trung bình)\n"
                        f"⚡ **RSI:** `{rsi:.1f}` | 💠 **MACD:** `{macd:.2f}`\n"
                        f"📋 **Bảng giá:** Trần `{tham_chieu*1.07:,.2f}` | Sàn `{tham_chieu*0.93:,.2f}` | TC `{tham_chieu:,.2f}`\n\n"
                        f"🤖 **HÀNH ĐỘNG:**\n👉 {loi_khuyen}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    await channel.send(content=msg, file=discord.File(fp=buf, filename=f"{ma}.png"))
        except: pass
        await asyncio.sleep(1.5)
    bot_vua_khoi_dong = False

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} BẢN HOÀN CHỈNH 24/7 đã sẵn sàng!')
    if not quet_bang_dien.is_running(): quet_bang_dien.start()
    if not quet_tin_tuc.is_running(): quet_tin_tuc.start()

# KHỞI ĐỘNG WEB SERVER TRƯỚC KHI CHẠY BOT (CHỐNG SLEEP)
if __name__ == "__main__":
    keep_alive() 
    if TOKEN: bot.run(TOKEN)
