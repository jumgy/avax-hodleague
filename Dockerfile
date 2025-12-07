FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Порт 6000
EXPOSE 6000

# Запуск вашего мейна
CMD ["python", "main.py"]