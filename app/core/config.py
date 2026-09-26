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