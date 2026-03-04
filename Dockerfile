# Dùng bản Python 3.10 mượt và nhẹ
FROM python:3.10-slim

# Đặt thư mục làm việc
WORKDIR /app

# Copy và cài đặt các thư viện cần thiết
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào
COPY . .

# Mở port 8080 cho Flask server chạy
EXPOSE 8080

# Chạy file main
CMD ["python", "main.py"]