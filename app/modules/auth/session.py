# app/modules/auth/session.py
import time
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import SECRET_KEY, SESSION_TIMEOUT_HOURS, SESSION_REMEMBER_DAYS

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")

COOKIE_NAME = "mini_erp_session"


def create_session_token(user_id: int, remember: bool = False) -> str:
    """
    Tạo session token.
    - Không remember: hết hạn sau 8 giờ.
    - Remember: hết hạn sau 30 ngày.
    """
    duration = (SESSION_REMEMBER_DAYS * 24 * 3600) if remember \
        else (SESSION_TIMEOUT_HOURS * 3600)
    payload = {
        "uid": user_id,
        "exp": time.time() + duration,
    }
    return serializer.dumps(payload)


def read_session_token(token: str) -> Optional[int]:
    """
    Đọc session token. Trả về user_id hoặc None nếu invalid/hết hạn.
    """
    if not token:
        return None
    max_age = SESSION_REMEMBER_DAYS * 24 * 3600  # Max có thể có
    try:
        data = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

    # Check expires_at bên trong payload
    if data.get("exp", 0) < time.time():
        return None

    return data.get("uid")