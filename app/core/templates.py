# app/core/templates.py
from fastapi.templating import Jinja2Templates
from app.core.config import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def set_global_modules(modules: list):
    """Đăng ký biến `modules` toàn cục cho mọi template."""
    templates.env.globals["modules"] = modules