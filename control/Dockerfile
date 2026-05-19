FROM python:3.11-slim

WORKDIR /app

RUN echo "https://mirrors.aliyun.com/pypi/simple/" > /etc/pip.conf || true && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates sudo git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY app.py .

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "app:create_app()"]
