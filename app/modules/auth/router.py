# app/modules/auth/router.py
from urllib.parse import quote
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.core.config import SESSION_TIMEOUT_HOURS, SESSION_REMEMBER_DAYS
from app.modules.auth import services
from app.modules.auth.session import (
    create_session_token, read_session_token, COOKIE_NAME,
)
from app.modules.auth.dependencies import (
    require_login, require_admin, require_permission,
)
from app.modules.auth.schemas import (
    UserCreate, UserUpdate, UserChangePassword,
    RoleCreate, RoleUpdate, ProfileUpdate,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ============================================================
# HELPERS
# ============================================================
def _to_int_list(values) -> list:
    """Chuyển list string thành list int."""
    if not values:
        return []
    result = []
    for v in values:
        try:
            result.append(int(v))
        except (ValueError, TypeError):
            pass
    return result


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# LOGIN / LOGOUT
# ============================================================
@router.get("/login")
def login_page(request: Request, next: str = "/"):
    token = request.cookies.get(COOKIE_NAME)
    if token and read_session_token(token):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="auth/login.html",
        context={"next": next, "error": None},
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember: str = Form(""),
    next: str = Form("/"),
    session: Session = Depends(get_session),
):
    ip = request.client.host if request.client else ""
    user, msg = services.authenticate(session, username, password, ip=ip)

    if not user:
        return templates.TemplateResponse(
            request=request, name="auth/login.html",
            context={"next": next, "error": msg, "username": username},
        )

    is_remember = remember in ("on", "true", "1")
    token = create_session_token(user.id, remember=is_remember)
    max_age = (SESSION_REMEMBER_DAYS * 24 * 3600) if is_remember \
        else (SESSION_TIMEOUT_HOURS * 3600)

    response = RedirectResponse(url=next or "/", status_code=303)
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=max_age, httponly=True, samesite="lax",
    )
    return response


@router.get("/logout")
def logout(request: Request, session: Session = Depends(get_session)):
    uid = getattr(request.state, "user_id", None)
    if uid:
        services.write_audit(
            session, uid, "LOGOUT", "", None,
            description="Đăng xuất",
            ip=request.client.host if request.client else "",
        )
        session.commit()
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ============================================================
# USER CRUD
# ============================================================
@router.get("/users")
def user_list(
    request: Request, q: str = "",
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    users = services.get_all_users(session, keyword=q)

    # Lấy roles cho từng user
    user_roles = {}
    for u in users:
        user_roles[u.id] = services.get_roles_of_user(session, u.id)

    return templates.TemplateResponse(
        request=request, name="auth/user_list.html",
        context={
            "users": users, "keyword": q, "user": user,
            "user_roles": user_roles,
        },
    )


@router.get("/users/new")
def user_new_form(
    request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    roles = services.get_all_roles(session)
    return templates.TemplateResponse(
        request=request, name="auth/user_form.html",
        context={
            "edit_user": None, "is_edit": False, "user": user,
            "roles": roles, "selected_role_ids": [],
        },
    )


@router.get("/users/{uid}/edit")
def user_edit_form(
    uid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    edit_user = services.get_user_by_id(session, uid)
    if not edit_user:
        return _redirect_with_msg("/auth/users", "error", "User không tồn tại")

    roles = services.get_all_roles(session)
    selected = services.get_role_ids_of_user(session, uid)

    return templates.TemplateResponse(
        request=request, name="auth/user_form.html",
        context={
            "edit_user": edit_user, "is_edit": True, "user": user,
            "roles": roles, "selected_role_ids": selected,
        },
    )


@router.post("/users/create")
async def user_create(
    request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    phone = form.get("phone", "").strip()
    note = form.get("note", "").strip()
    role_ids = _to_int_list(form.getlist("role_ids"))

    new_user, msg = services.create_user(session, UserCreate(
        username=username, password=password, full_name=full_name,
        email=email, phone=phone, role_ids=role_ids, note=note,
    ), created_by=user.id)

    if not new_user:
        return _redirect_with_msg("/auth/users", "error", msg)

    services.write_audit(
        session, user.id, "CREATE", "auth_user", new_user.id,
        new_value={"username": username, "full_name": full_name, "roles": role_ids},
        description=f"Tạo user {username}",
        ip=request.client.host if request.client else "",
    )
    session.commit()
    return _redirect_with_msg("/auth/users", "success", f"Đã tạo user {username}")


@router.post("/users/{uid}/update")
async def user_update(
    uid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    form = await request.form()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    phone = form.get("phone", "").strip()
    status = form.get("status", "ACTIVE")
    note = form.get("note", "").strip()
    role_ids = _to_int_list(form.getlist("role_ids"))

    old_user = services.get_user_by_id(session, uid)
    old_data = {
        "full_name": old_user.full_name if old_user else "",
        "status": old_user.status if old_user else "",
        "roles": services.get_role_ids_of_user(session, uid),
    } if old_user else None

    updated, msg = services.update_user(session, uid, UserUpdate(
        full_name=full_name, email=email, phone=phone,
        status=status, role_ids=role_ids, note=note,
    ))

    if not updated:
        return _redirect_with_msg(f"/auth/users/{uid}/edit", "error", msg)

    services.write_audit(
        session, user.id, "UPDATE", "auth_user", uid,
        old_value=old_data,
        new_value={"full_name": full_name, "status": status, "roles": role_ids},
        description=f"Cập nhật user {updated.username}",
        ip=request.client.host if request.client else "",
    )
    session.commit()
    return _redirect_with_msg("/auth/users", "success", f"Đã cập nhật user")


@router.post("/users/{uid}/delete")
def user_delete(
    uid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    # Không cho tự xóa
    if uid == user.id:
        return _redirect_with_msg("/auth/users", "error", "Không thể xóa chính mình")

    target = services.get_user_by_id(session, uid)
    username = target.username if target else ""

    ok, msg = services.delete_user(session, uid)
    if ok:
        services.write_audit(
            session, user.id, "DELETE", "auth_user", uid,
            old_value={"username": username},
            description=f"Xóa user {username}",
            ip=request.client.host if request.client else "",
        )
        session.commit()
    return _redirect_with_msg("/auth/users",
                               "success" if ok else "error", msg)


@router.post("/users/{uid}/reset-password")
def user_reset_password(
    uid: int, request: Request,
    new_password: str = Form(...),
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    ok, msg = services.reset_password_admin(session, uid, new_password)
    if ok:
        services.write_audit(
            session, user.id, "RESET_PASSWORD", "auth_user", uid,
            description=f"Reset mật khẩu cho user #{uid}",
            ip=request.client.host if request.client else "",
        )
        session.commit()
    return _redirect_with_msg("/auth/users",
                               "success" if ok else "error", msg)


# ============================================================
# ROLE CRUD
# ============================================================
@router.get("/roles")
def role_list(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    roles = services.get_all_roles(session)

    # Đếm user + permission cho từng role
    role_stats = {}
    for r in roles:
        from sqlmodel import select, func
        from app.modules.auth.models import UserRole, RolePermission

        user_count = session.exec(
            select(func.count()).select_from(UserRole)
            .where(UserRole.role_id == r.id)
        ).one() or 0
        perm_count = session.exec(
            select(func.count()).select_from(RolePermission)
            .where(RolePermission.role_id == r.id)
        ).one() or 0
        role_stats[r.id] = {"users": user_count, "permissions": perm_count}

    return templates.TemplateResponse(
        request=request, name="auth/role_list.html",
        context={"roles": roles, "role_stats": role_stats, "user": user},
    )


@router.get("/roles/new")
def role_new_form(
    request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    perm_grouped = services.get_permissions_by_module(session)
    return templates.TemplateResponse(
        request=request, name="auth/role_form.html",
        context={
            "edit_role": None, "is_edit": False, "user": user,
            "perm_grouped": perm_grouped, "selected_perm_ids": [],
        },
    )


@router.get("/roles/{rid}/edit")
def role_edit_form(
    rid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    edit_role = services.get_role(session, rid)
    if not edit_role:
        return _redirect_with_msg("/auth/roles", "error", "Vai trò không tồn tại")

    perm_grouped = services.get_permissions_by_module(session)
    selected = services.get_permission_ids_of_role(session, rid)

    return templates.TemplateResponse(
        request=request, name="auth/role_form.html",
        context={
            "edit_role": edit_role, "is_edit": True, "user": user,
            "perm_grouped": perm_grouped, "selected_perm_ids": selected,
        },
    )


@router.post("/roles/create")
async def role_create(
    request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    form = await request.form()
    code = form.get("code", "").strip().upper()
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    perm_ids = _to_int_list(form.getlist("permission_ids"))

    new_role, msg = services.create_role(session, RoleCreate(
        code=code, name=name, description=description,
        permission_ids=perm_ids,
    ))

    if not new_role:
        return _redirect_with_msg("/auth/roles", "error", msg)

    services.write_audit(
        session, user.id, "CREATE", "auth_role", new_role.id,
        new_value={"code": code, "name": name, "permissions": perm_ids},
        description=f"Tạo vai trò {code}",
        ip=request.client.host if request.client else "",
    )
    session.commit()
    return _redirect_with_msg("/auth/roles", "success", f"Đã tạo vai trò {code}")


@router.post("/roles/{rid}/update")
async def role_update(
    rid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    form = await request.form()
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    perm_ids = _to_int_list(form.getlist("permission_ids"))

    old_role = services.get_role(session, rid)
    old_data = {
        "name": old_role.name if old_role else "",
        "permissions": services.get_permission_ids_of_role(session, rid),
    } if old_role else None

    updated, msg = services.update_role(session, rid, RoleUpdate(
        name=name, description=description, permission_ids=perm_ids,
    ))

    if not updated:
        return _redirect_with_msg(f"/auth/roles/{rid}/edit", "error", msg)

    services.write_audit(
        session, user.id, "UPDATE", "auth_role", rid,
        old_value=old_data,
        new_value={"name": name, "permissions": perm_ids},
        description=f"Cập nhật vai trò {updated.code}",
        ip=request.client.host if request.client else "",
    )
    session.commit()
    return _redirect_with_msg("/auth/roles", "success", "Đã cập nhật vai trò")


@router.post("/roles/{rid}/delete")
def role_delete(
    rid: int, request: Request,
    user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    target = services.get_role(session, rid)
    code = target.code if target else ""

    ok, msg = services.delete_role(session, rid)
    if ok:
        services.write_audit(
            session, user.id, "DELETE", "auth_role", rid,
            old_value={"code": code},
            description=f"Xóa vai trò {code}",
            ip=request.client.host if request.client else "",
        )
        session.commit()
    return _redirect_with_msg("/auth/roles",
                               "success" if ok else "error", msg)


# ============================================================
# PROFILE
# ============================================================
@router.get("/profile")
def profile_page(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    roles = services.get_roles_of_user(session, user.id)
    perm_codes = services.get_permission_codes_of_user(session, user.id)
    return templates.TemplateResponse(
        request=request, name="auth/profile.html",
        context={
            "user": user, "roles": roles,
            "perm_count": len(perm_codes),
        },
    )


@router.post("/profile/update")
def profile_update(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    updated, msg = services.update_profile(session, user.id, ProfileUpdate(
        full_name=full_name, email=email, phone=phone,
    ))
    return _redirect_with_msg("/auth/profile",
                               "success" if updated else "error", msg)


@router.post("/profile/change-password")
def profile_change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if new_password != confirm_password:
        return _redirect_with_msg("/auth/profile", "error", "Mật khẩu xác nhận không khớp")

    if len(new_password) < 4:
        return _redirect_with_msg("/auth/profile", "error", "Mật khẩu phải từ 4 ký tự")

    ok, msg = services.change_password(session, user.id, UserChangePassword(
        old_password=old_password, new_password=new_password,
    ))
    if ok:
        services.write_audit(
            session, user.id, "CHANGE_PASSWORD", "auth_user", user.id,
            description="Đổi mật khẩu",
            ip=request.client.host if request.client else "",
        )
        session.commit()
    return _redirect_with_msg("/auth/profile",
                               "success" if ok else "error", msg)


# ============================================================
# AUDIT LOG
# ============================================================
@router.get("/audit-log")
def audit_log_page(
    request: Request, q: str = "",
    action: str = "", model: str = "",
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    logs = services.get_audit_logs(
        session, keyword=q, action=action, model=model, limit=300,
    )
    return templates.TemplateResponse(
        request=request, name="auth/audit_log.html",
        context={
            "logs": logs, "user": user,
            "keyword": q, "filter_action": action, "filter_model": model,
        },
    )