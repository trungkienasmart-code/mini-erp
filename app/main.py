import importlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import APP_NAME, APP_VERSION, STATIC_DIR, TEMPLATES_DIR
from app.core.database import create_db_and_tables

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --- Cơ chế tự động phát hiện và đăng ký module ---
MODULES_DIR = Path(__file__).parent / "modules"
ACTIVE_MODULES = []

def load_modules():
    """Quét thư mục modules/, đăng ký router và thu thập menu."""
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

        # Đăng ký router
        if hasattr(router_module, "router"):
            app.include_router(router_module.router)

        # Thu thập manifest
        if hasattr(manifest_module, "MANIFEST"):
            ACTIVE_MODULES.append(manifest_module.MANIFEST)
            print(f"✅ Đã nạp module: {manifest_module.MANIFEST['name']}")

@app.on_event("startup")
def on_startup():
    load_modules()           # Nạp module trước (để import các models)
    create_db_and_tables()   # Sau đó mới tạo bảng trong CSDL

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": APP_NAME,
            "version": APP_VERSION,
            "modules": ACTIVE_MODULES,
        },
    )