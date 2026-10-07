# app/core/database.py
from sqlmodel import SQLModel, Session, create_engine
from app.core.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def _import_all_models():
    """Import tất cả models để SQLModel biết cần tạo bảng nào."""
    try:
        from app.modules.auth import models as _auth_models
    except ImportError:
        pass
    try:
        from app.modules.quan_ly_kho import models as _kho_models
    except ImportError:
        pass
    try:
        from app.modules.ban_hang import models as _bh_models
    except ImportError:
        pass
    try:
        from app.modules.mua_hang import models as _mh_models
    except ImportError:
        pass
    try:
        from app.modules.ke_toan import models as _kt_models
    except ImportError:
        pass
    try:
        from app.modules.noi_bo import models as _nb_models
    except ImportError:
        pass


def create_db_and_tables():
    _import_all_models()
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session