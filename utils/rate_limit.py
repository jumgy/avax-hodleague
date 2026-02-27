"""
Shared rate limiter for the API. Use this instance in all routes so that
app.state.limiter (set in main.py) and decorators use the same storage.

default_limits: общий лимит на все маршруты (парсеры/скраперы не смогут дергать API без ограничений).
Отдельные эндпоинты могут ужесточать лимит (@limiter.limit). Исключения — через @limiter.exempt.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 300 запросов в минуту с одного IP по умолчанию на все маршруты
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300/minute"],
)
