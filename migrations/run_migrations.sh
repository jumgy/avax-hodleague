#!/bin/bash
# migrations/run_migrations.sh

echo "🚀 Running database migrations..."

cd "$(dirname "$0")/../"

# Активируем virtual environment если есть
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "📦 Virtual environment activated"
fi

# Запускаем миграции
python migrations/migration_runner.py

echo "🎉 Migrations completed!"