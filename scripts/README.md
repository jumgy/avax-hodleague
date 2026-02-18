# Development Scripts

Набор автоматизированных скриптов для разработки Fantasy Crypto Tournament бэкенда.

## Быстрый старт

Все задачи интегрированы в VS Code/Cursor:

1. Нажмите `Ctrl+Shift+P` (Windows) или `Cmd+Shift+P` (macOS)
2. Выберите **Tasks: Run Task**
3. Выберите нужную задачу из списка

## Доступные задачи

### 🧪 Тестирование

- **Run Tests** - запуск всех тестов
- **Run Tests with Coverage** - тесты с отчетом о покрытии
- **Run Single Test File** - запуск текущего файла теста

**CLI альтернативы:**
```powershell
# Все тесты
pytest -v

# С покрытием
.\scripts\run_tests.ps1 -Coverage

# Один файл
.\scripts\run_tests.ps1 -File tests/test_scoring.py

# По ключевому слову
.\scripts\run_tests.ps1 -Keyword "tournament"

# Fail fast (остановка на первой ошибке)
.\scripts\run_tests.ps1 -FailFast
```

### 🔍 Линтинг и форматирование

- **Lint (Ruff)** - проверка кода на ошибки
- **Lint & Fix (Ruff)** - автоматическое исправление
- **Format (Ruff)** - форматирование кода
- **Type Check (mypy)** - проверка типов
- **Full Check** - все проверки сразу

**CLI альтернативы:**
```powershell
# Только проверка
.\scripts\lint.ps1

# С автофиксом
.\scripts\lint.ps1 -Fix

# С проверкой типов
.\scripts\lint.ps1 -TypeCheck

# Все вместе
.\scripts\lint.ps1 -All

# Конкретный путь
.\scripts\lint.ps1 -Fix -Path api/routes/tournaments.py
```

### 🗄️ Миграции базы данных

- **Create Migration** - создать новую миграцию
- **Run Migrations** - применить миграции
- **Rollback Migration** - откатить последнюю миграцию
- **Show Migration History** - история миграций

**CLI альтернативы:**
```powershell
# Создать миграцию (интерактивно)
.\scripts\create_migration.ps1

# С сообщением
.\scripts\create_migration.ps1 -Message "add user notifications table"

# Применить миграции
alembic upgrade head

# Откатить последнюю
alembic downgrade -1

# История
alembic history --verbose

# Текущая версия
alembic current
```

### 🐳 Docker окружение

- **Start Dev Environment** - запустить dev-окружение
- **Stop Dev Environment** - остановить
- **Restart Dev Environment** - перезапустить
- **Show Dev Logs** - показать логи

**CLI альтернативы:**
```powershell
# Запустить
.\scripts\docker_dev.ps1 start

# Остановить
.\scripts\docker_dev.ps1 stop

# Перезапустить
.\scripts\docker_dev.ps1 restart

# Статус
.\scripts\docker_dev.ps1 status

# Логи
.\scripts\docker_dev.ps1 logs -Follow

# Логи конкретного сервиса
.\scripts\docker_dev.ps1 logs -Service postgres -Follow

# Пересборка (долго!)
.\scripts\docker_dev.ps1 rebuild

# Очистить все (включая БД!)
.\scripts\docker_dev.ps1 clean
```

### 🎨 Генераторы кода

- **Create New Endpoint** - создать новый API-эндпоинт

**CLI альтернатива:**
```powershell
# Интерактивно
.\scripts\create_endpoint.ps1

# С именем ресурса
.\scripts\create_endpoint.ps1 -Name notification
```

#### Что создается при генерации эндпоинта:

1. **Router** (`api/routes/{resource}s.py`):
   - GET /resources - список
   - GET /resources/{id} - один элемент
   - POST /resources - создание (с auth)
   - DELETE /resources/{id} - удаление (с auth)
   - Pydantic схемы (Request/Response)
   - Готовая обработка ошибок

2. **Service** (`services/{resource}_service.py`):
   - CRUD операции
   - Логирование с emoji
   - Обработка транзакций

3. **Tests** (`tests/test_{resource}.py`):
   - Тесты для всех эндпоинтов
   - Проверки auth
   - Placeholder'ы для расширения

**После генерации нужно:**
1. Создать модель в `models/{resource}_models.py`
2. Обновить service для работы с моделью
3. Зарегистрировать router в `main.py`
4. Создать миграцию для модели
5. Запустить тесты

### 🚀 Dev сервер

- **Run Server (Dev)** - запуск uvicorn с hot-reload

```powershell
# Или напрямую
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Keyboard shortcuts

Можно настроить горячие клавиши в VS Code/Cursor:

1. `Ctrl+Shift+P` → **Preferences: Open Keyboard Shortcuts (JSON)**
2. Добавить:

```json
[
  {
    "key": "ctrl+shift+t",
    "command": "workbench.action.tasks.runTask",
    "args": "🧪 Run Tests"
  },
  {
    "key": "ctrl+shift+l",
    "command": "workbench.action.tasks.runTask",
    "args": "✅ Full Check (Lint + Format + Type)"
  }
]
```

## Рекомендуемый workflow

### Перед коммитом
```powershell
# 1. Проверить код
.\scripts\lint.ps1 -All

# 2. Запустить тесты
.\scripts\run_tests.ps1 -Coverage

# 3. Проверить покрытие
# Открыть htmlcov/index.html в браузере
```

### Создание новой фичи
```powershell
# 1. Создать эндпоинт
.\scripts\create_endpoint.ps1 -Name feature

# 2. Создать модель (вручную)
# models/feature_models.py

# 3. Создать миграцию
.\scripts\create_migration.ps1 -Message "add feature table"

# 4. Обновить service (вручную)
# services/feature_service.py

# 5. Запустить тесты
.\scripts\run_tests.ps1 -File tests/test_feature.py

# 6. Проверить линтинг
.\scripts\lint.ps1 -Fix
```

## Установка dev-зависимостей

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Troubleshooting

### PowerShell Execution Policy
Если скрипты не выполняются:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Ruff не найден
```powershell
pip install ruff
```

### mypy не найден
```powershell
pip install mypy
```

### pytest-cov не найден
```powershell
pip install pytest-cov
```

## Дополнительно

Все скрипты находятся в `scripts/`:
- `create_endpoint.ps1` - генератор эндпоинтов
- `create_migration.ps1` - создание миграций
- `run_tests.ps1` - запуск тестов
- `lint.ps1` - линтинг и форматирование
- `docker_dev.ps1` - управление Docker

VS Code tasks в `.vscode/tasks.json`.
