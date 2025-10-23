# Base Python image
FROM python:3.11-slim

# 1. FFmpeg ko system mein install karna
# Apt-get update ke baad FFmpeg aur uski zaroori tools ko install karen
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Application code aur dependencies set karna
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Application code copy karna
COPY . /app

# 4. Port aur server chalu karna
# Gunicorn is used by default for Flask apps in Flexible environment/Cloud Run
ENV PORT 8080
CMD exec gunicorn --bind :$PORT --workers 4 --threads 2 application:application
