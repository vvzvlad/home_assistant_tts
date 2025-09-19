FROM python:3.11-slim

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libportaudio2 \
       libsndfile1 \
       ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p data
RUN mkdir -p model
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .

CMD ["python", "tts_server.py"]