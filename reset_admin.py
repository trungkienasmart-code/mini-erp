from app.core.database import engine
from sqlmodel import Session, select
from app.modules.auth.models import User
from app.modules.auth.services import hash_password

s = Session(engine)
admin = s.exec(select(User).where(User.username == "admin")).first()
if admin:
    admin.password_hash = hash_password("admin123")
    admin.must_change_password = False
    s.add(admin)
    s.commit()
    print("✅ Đã reset mật khẩu admin về: admin123")
else:
    print("❌ Không tìm thấy user admin")