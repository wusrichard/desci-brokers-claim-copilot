"""Web 邊界的安全設定：模式、CORS、CSRF、節流與回應標頭。"""

import hmac
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


TRUST_MODE = os.environ.get("AGENT_TRUST_MODE", "demo").strip().lower()
IS_DEMO = TRUST_MODE == "demo"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
MAX_BODY_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(1024 * 1024)))
ALLOW_PUBLIC_REGISTRATION = os.environ.get(
    "ALLOW_PUBLIC_REGISTRATION", "1" if IS_DEMO else "0"
) == "1"
ENABLE_TAMPER_DEMO = os.environ.get(
    "ENABLE_TAMPER_DEMO", "1" if IS_DEMO else "0"
) == "1"

ALLOWED_ORIGINS = [
    value.strip()
    for value in os.environ.get(
        "ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
    ).split(",")
    if value.strip()
]

_attempts = defaultdict(deque)
_attempts_lock = threading.Lock()
LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS = 8


def check_login_rate_limit(key: str) -> None:
    """單程序 Demo 節流；正式部署應改用 Redis／API gateway。"""
    now = time.monotonic()
    with _attempts_lock:
        bucket = _attempts[key]
        while bucket and now - bucket[0] > LOGIN_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(429, "登入嘗試過多，請稍後再試")
        bucket.append(now)


def clear_login_attempts(key: str) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)


def enforce_csrf(request: Request) -> None:
    """Cookie 認證的變更請求使用 double-submit CSRF；Bearer API client 不受影響。"""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.url.path in ("/login", "/register"):
        return
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    if not request.cookies.get("session"):
        return
    cookie_value = request.cookies.get("csrf_token", "")
    header_value = request.headers.get("x-csrf-token", "")
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(403, "CSRF 驗證失敗")


def add_security_headers(response) -> None:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
