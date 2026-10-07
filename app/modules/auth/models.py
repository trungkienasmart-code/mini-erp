# app/modules/auth/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# NGƯỜI DÙNG
# ============================================================
class User(SQLModel, table=True):
    __tablename__ = "auth_user"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, index=True, unique=True)
    password_hash: str = Field(max_length=255)
    full_name: str = Field(max_length=100)
    email: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=30)

    status: str = Field(default="ACTIVE", max_length=20)
    # ACTIVE / LOCKED / SUSPENDED

    must_change_password: bool = Field(default=False)
    last_login_at: Optional[datetime] = Field(default=None)
    last_login_ip: str = Field(default="", max_length=50)

    created_by: Optional[int] = Field(default=None, foreign_key="auth_user.id")
    note: str = Field(default="", max_length=500)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# VAI TRÒ
# ============================================================
class Role(SQLModel, table=True):
    __tablename__ = "auth_role"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    is_system: bool = Field(default=False)  # Không cho xóa nếu là system

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# USER - ROLE (N-N)
# ============================================================
class UserRole(SQLModel, table=True):
    __tablename__ = "auth_user_role"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="auth_user.id", index=True)
    role_id: int = Field(foreign_key="auth_role.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# QUYỀN
# ============================================================
class Permission(SQLModel, table=True):
    __tablename__ = "auth_permission"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=100, index=True, unique=True)
    # VD: sales.pos.use, inventory.product.edit
    name: str = Field(max_length=200)
    module: str = Field(max_length=50, index=True)
    # inventory, sales, purchase, accounting, auth, internal
    action: str = Field(default="", max_length=20)
    # view, create, edit, delete, approve, other
    description: str = Field(default="", max_length=500)
    order_index: int = Field(default=0)


# ============================================================
# ROLE - PERMISSION (N-N)
# ============================================================
class RolePermission(SQLModel, table=True):
    __tablename__ = "auth_role_permission"

    id: Optional[int] = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="auth_role.id", index=True)
    permission_id: int = Field(foreign_key="auth_permission.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# AUDIT LOG
# ============================================================
class AuditLog(SQLModel, table=True):
    __tablename__ = "auth_audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    username: str = Field(default="", max_length=50)

    action: str = Field(max_length=50, index=True)
    # LOGIN / LOGOUT / CREATE / UPDATE / DELETE / APPROVE / LOCK / ...

    model: str = Field(default="", max_length=100, index=True)
    # sale_order, purchase_order, voucher, ...

    record_id: Optional[int] = Field(default=None, index=True)
    description: str = Field(default="", max_length=500)

    old_value: str = Field(default="", max_length=2000)  # JSON
    new_value: str = Field(default="", max_length=2000)  # JSON

    ip_address: str = Field(default="", max_length=50)
    user_agent: str = Field(default="", max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)