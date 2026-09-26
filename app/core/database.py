from sqlmodel import SQLModel, Session, create_engine
from app.core.config import DATABASE_URL

# check_same_thread=False cần thiết cho SQLite khi dùng với FastAPI
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Đổi thành True nếu muốn xem câu lệnh SQL khi debug
    connect_args={"check_same_thread": False},
)

def create_db_and_tables():
    """Tạo toàn bộ bảng dựa trên các model đã đăng ký."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Dependency để lấy session trong các router."""
    with Session(engine) as session:
        yield session