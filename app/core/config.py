import secrets
from pathlib import Path
from pathlib import Path

# Thư mục gốc của dự án (mini-erp)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Đường dẫn file SQLite (sẽ tự động tạo khi chạy)
DATABASE_URL = f"sqlite:///{BASE_DIR / 'database.db'}"

# Thông tin ứng dụng
APP_NAME = "Mini ERP"
APP_VERSION = "0.1.0"

# Thư mục templates và static
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

# ============================================================
# SECRET KEY (dùng cho session cookie)
# ============================================================
SECRET_FILE = BASE_DIR / ".secret_key"

if SECRET_FILE.exists():
    SECRET_KEY = SECRET_FILE.read_text(encoding="utf-8").strip()
else:
    SECRET_KEY = secrets.token_urlsafe(32)
    SECRET_FILE.write_text(SECRET_KEY, encoding="utf-8")

# Session timeout
SESSION_TIMEOUT_HOURS = 8       # Không remember
SESSION_REMEMBER_DAYS = 30      # Có remember