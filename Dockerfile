FROM python:3.11-slim

WORKDIR /app
RUN mkdir -p data
RUN mkdir -p model
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .

CMD ["python", "tts_server.py"]