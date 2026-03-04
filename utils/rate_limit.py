"""
Shared rate limiter for the API. Use this instance in all routes so that
app.state.limiter (set in main.py) and decorators use the same storage.

default_limits: global limit for all routes (parsers/scrapers cannot hit the API without limits).
Individual endpoints may tighten the limit via @limiter.limit. Exempt via @limiter.exempt.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 300 requests per minute per IP by default for all routes.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300/minute"],
)
