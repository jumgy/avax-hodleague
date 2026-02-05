FROM python:3.11-slim

# Создаём непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .


# Меняем владельца (важно для non-root)
RUN chown -R appuser:appuser /app

# Переключаемся на непривилегированного пользователя
USER appuser

ARG PORT=8000
ENV PORT=${PORT}
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --no-access-log