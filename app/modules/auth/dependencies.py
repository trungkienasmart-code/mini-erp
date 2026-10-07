# app/modules/auth/dependencies.py
from fastapi import Depends, Request, HTTPException
from sqlmodel import Session
from typing import Optional

from app.core.database import get_session
from app.modules.auth.models import User
from app.modules.auth import services


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """
    Lấy user đang đăng nhập. Trả về None nếu chưa login (không raise).
    Dùng cho các route optional.
    """
    uid = getattr(request.state, "user_id", None)
    if not uid:
        return None
    user = session.get(User, uid)
    if not user or user.status != "ACTIVE":
        return None
    return user


def require_login(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Yêu cầu đăng nhập. Raise 401 nếu chưa login."""
    if not user:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập")
    return user


def require_permission(code: str):
    """
    Factory: Trả về dependency yêu cầu user có permission cụ thể.
    Dùng: user = Depends(require_permission("sales.pos.use"))
    """
    def checker(
        user: User = Depends(require_login),
        session: Session = Depends(get_session),
    ) -> User:
        if not services.has_permission(session, user.id, code):
            raise HTTPException(
                status_code=403,
                detail=f"Không có quyền: {code}",
            )
        return user
    return checker


def require_admin(
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> User:
    """Yêu cầu role ADMIN."""
    if not services.is_admin(session, user.id):
        raise HTTPException(status_code=403, detail="Cần quyền Admin")
    return user
