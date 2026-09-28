FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Site web (builds & compos), lancé dans le même process que le bot — voir bot.py
EXPOSE 8080

CMD ["python", "bot.py"]
