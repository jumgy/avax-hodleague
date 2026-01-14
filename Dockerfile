FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

ARG PORT=8000
ENV PORT=${PORT}
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --no-access-log