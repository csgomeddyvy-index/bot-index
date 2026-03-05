# Dùng môi trường Python 3.10 bản slim (nhẹ, tiết kiệm RAM)
FROM python:3.10-slim

# Đặt thư mục làm việc mặc định bên trong container
WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết để vẽ biểu đồ
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements.txt vào trước để cài đặt thư viện
COPY requirements.txt .

# Cài đặt thư viện Python
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn của bạn vào container
COPY . .

# Lệnh khởi động bot
CMD ["python", "main.py"]
