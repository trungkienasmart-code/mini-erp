import importlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import APP_NAME, APP_VERSION, STATIC_DIR
from app.core.database import create_db_and_tables
from app.core.templates import templates, set_global_modules

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

MODULES_DIR = Path(__file__).parent / "modules"
ACTIVE_MODULES = []

# Các đường dẫn KHÔNG cần đăng nhập
PUBLIC_PATHS = (
    "/auth/login",
    "/auth/logout",
    "/static",
    "/favicon.ico",
)


def load_modules():
    for folder in sorted(MODULES_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        router_module_path = f"app.modules.{folder.name}.router"
        manifest_path = f"app.modules.{folder.name}.manifest"

        try:
            router_module = importlib.import_module(router_module_path)
            manifest_module = importlib.import_module(manifest_path)
        except ModuleNotFoundError:
            continue

        if hasattr(router_module, "router"):
            app.include_router(router_module.router)

        if hasattr(manifest_module, "MANIFEST"):
            ACTIVE_MODULES.append(manifest_module.MANIFEST)
            print(f"✅ Đã nạp module: {manifest_module.MANIFEST['name']}")


@app.on_event("startup")
def on_startup():
    load_modules()
    set_global_modules(ACTIVE_MODULES)
    create_db_and_tables()

    # Seed data cho module auth
    from sqlmodel import Session
    from app.core.database import engine
    from app.modules.auth.services import seed_data
    with Session(engine) as s:
        seed_data(s)


# ============================================================
# MIDDLEWARE: Check session cho mọi request
# ============================================================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Bỏ qua các path public
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    # Đọc token
    from app.modules.auth.session import read_session_token, COOKIE_NAME
    token = request.cookies.get(COOKIE_NAME)
    uid = read_session_token(token) if token else None

    if not uid:
        # Chưa login → redirect đến trang login
        next_url = path
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(
            url=f"/auth/login?next={next_url}",
            status_code=303,
        )

    # Gắn user vào request.state
    request.state.user_id = uid

    # Load user object + permissions (cache vào request.state)
    from sqlmodel import Session
    from app.core.database import engine
    from app.modules.auth.models import User
    from app.modules.auth.services import get_permission_codes_of_user, is_admin

    with Session(engine) as s:
        user = s.get(User, uid)
        if user and user.status == "ACTIVE":
            request.state.user = user
            # Admin: cấp hết quyền (kể cả quyền mới thêm sau này)
            if is_admin(s, uid):
                request.state.permissions = ["*"]  # Wildcard
            else:
                request.state.permissions = get_permission_codes_of_user(s, uid)
        else:
            # User bị khóa/xóa → logout
            response = RedirectResponse(url="/auth/login", status_code=303)
            response.delete_cookie(COOKIE_NAME)
            return response

    # === CHECK PERMISSION THEO URL ===
    user_perms = request.state.permissions or []
    is_super_admin = "*" in user_perms

    if not is_super_admin:
        from app.modules.auth.permissions_map import find_required_permission
        from app.modules.auth.services import get_roles_of_user

        found, required = find_required_permission(path)

        if found and required and required not in user_perms:
            # Trả về trang 403
            from sqlmodel import Session as Sess
            from app.core.database import engine as eng
            with Sess(eng) as s2:
                roles = get_roles_of_user(s2, uid)

            return templates.TemplateResponse(
                request=request,
                name="errors/403.html",
                context={
                    "user": request.state.user,
                    "required_permission": required,
                    "user_roles": roles,
                },
                status_code=403,
            )

    return await call_next(request)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": APP_NAME,
            "version": APP_VERSION,
        },
    )