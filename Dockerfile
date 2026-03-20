FROM --platform=linux/arm64 python:3.11.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

RUN useradd -r -u 1000 botuser && chown -R botuser /app
USER botuser

CMD ["python", "-u", "main.py"]
