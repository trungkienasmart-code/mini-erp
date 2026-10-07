# app/modules/auth/services.py
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
import json

from sqlmodel import Session, select, or_, func
from passlib.context import CryptContext

from app.modules.auth.models import (
    User, Role, UserRole, Permission, RolePermission, AuditLog,
)
from app.modules.auth.schemas import (
    UserCreate, UserUpdate, UserChangePassword,
    RoleCreate, RoleUpdate, ProfileUpdate,
)


# ============================================================
# PASSWORD HASHING
# ============================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password bằng bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Kiểm tra password có khớp hash không."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ============================================================
# USER - QUERY
# ============================================================
def get_user_by_id(session: Session, uid: int) -> Optional[User]:
    return session.get(User, uid)


def get_user_by_username(session: Session, username: str) -> Optional[User]:
    return session.exec(
        select(User).where(User.username == username)
    ).first()


def get_all_users(session: Session, keyword: str = "") -> List[User]:
    stmt = select(User)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(or_(
            User.username.like(p),
            User.full_name.like(p),
            User.email.like(p),
            User.phone.like(p),
        ))
    return list(session.exec(stmt.order_by(User.username)).all())


# ============================================================
# USER - CRUD
# ============================================================
def create_user(
    session: Session, data: UserCreate,
    created_by: Optional[int] = None,
) -> Tuple[Optional[User], str]:
    """Tạo user mới với password hash + gán roles."""
    try:
        existing = get_user_by_username(session, data.username)
        if existing:
            return None, f"Username '{data.username}' đã tồn tại"

        user = User(
            username=data.username.strip(),
            password_hash=hash_password(data.password),
            full_name=data.full_name.strip(),
            email=data.email.strip(),
            phone=data.phone.strip(),
            status="ACTIVE",
            must_change_password=True,  # Bắt đổi lần đầu
            created_by=created_by,
            note=data.note,
        )
        session.add(user)
        session.flush()

        # Gán roles
        for rid in data.role_ids:
            if session.get(Role, rid):
                session.add(UserRole(user_id=user.id, role_id=rid))

        session.commit()
        session.refresh(user)
        return user, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo user: {e}"


def update_user(
    session: Session, uid: int, data: UserUpdate,
) -> Tuple[Optional[User], str]:
    """Cập nhật thông tin user + roles."""
    try:
        user = session.get(User, uid)
        if not user:
            return None, "User không tồn tại"

        user.full_name = data.full_name.strip()
        user.email = data.email.strip()
        user.phone = data.phone.strip()
        user.status = data.status
        user.note = data.note
        user.updated_at = datetime.now(timezone.utc)
        session.add(user)

        # Xóa roles cũ
        session.exec(
            select(UserRole).where(UserRole.user_id == uid)
        )
        old_roles = session.exec(
            select(UserRole).where(UserRole.user_id == uid)
        ).all()
        for ur in old_roles:
            session.delete(ur)

        # Thêm roles mới
        for rid in data.role_ids:
            if session.get(Role, rid):
                session.add(UserRole(user_id=uid, role_id=rid))

        session.commit()
        session.refresh(user)
        return user, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi cập nhật: {e}"


def delete_user(session: Session, uid: int) -> Tuple[bool, str]:
    """Xóa user (không xóa được chính mình hoặc admin cuối cùng)."""
    user = session.get(User, uid)
    if not user:
        return False, "User không tồn tại"
    if user.username == "admin":
        return False, "Không thể xóa tài khoản admin"

    # Xóa roles
    urs = session.exec(select(UserRole).where(UserRole.user_id == uid)).all()
    for ur in urs:
        session.delete(ur)

    session.delete(user)
    session.commit()
    return True, "Đã xóa user"


def change_password(
    session: Session, uid: int, data: UserChangePassword,
) -> Tuple[bool, str]:
    """User tự đổi mật khẩu."""
    user = session.get(User, uid)
    if not user:
        return False, "User không tồn tại"

    if not verify_password(data.old_password, user.password_hash):
        return False, "Mật khẩu cũ không đúng"

    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return True, "Đã đổi mật khẩu"


def reset_password_admin(
    session: Session, uid: int, new_password: str,
) -> Tuple[bool, str]:
    """Admin reset mật khẩu cho user."""
    user = session.get(User, uid)
    if not user:
        return False, "User không tồn tại"

    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return True, f"Đã reset mật khẩu cho {user.username}"


def update_profile(
    session: Session, uid: int, data: ProfileUpdate,
) -> Tuple[Optional[User], str]:
    """Cập nhật profile (không đổi được username/roles)."""
    user = session.get(User, uid)
    if not user:
        return None, "User không tồn tại"

    user.full_name = data.full_name.strip()
    user.email = data.email.strip()
    user.phone = data.phone.strip()
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user, "OK"


# ============================================================
# LOGIN / LOGOUT
# ============================================================
def authenticate(
    session: Session, username: str, password: str, ip: str = "",
) -> Tuple[Optional[User], str]:
    """Đăng nhập: verify username + password."""
    user = get_user_by_username(session, username)
    if not user:
        return None, "Sai tên đăng nhập hoặc mật khẩu"
    if user.status == "LOCKED":
        return None, "Tài khoản đã bị khóa"
    if user.status == "SUSPENDED":
        return None, "Tài khoản đã bị tạm ngưng"
    if not verify_password(password, user.password_hash):
        return None, "Sai tên đăng nhập hoặc mật khẩu"

    # Cập nhật last login
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    session.add(user)
    session.commit()
    session.refresh(user)

    # Ghi audit
    write_audit(session, user.id, "LOGIN", "", None,
                description=f"Đăng nhập thành công", ip=ip)

    return user, "OK"


# ============================================================
# ROLE
# ============================================================
def get_all_roles(session: Session) -> List[Role]:
    return list(session.exec(select(Role).order_by(Role.code)).all())


def get_role(session: Session, rid: int) -> Optional[Role]:
    return session.get(Role, rid)


def get_roles_of_user(session: Session, uid: int) -> List[Role]:
    """Lấy danh sách role của user."""
    stmt = (
        select(Role)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == uid)
    )
    return list(session.exec(stmt).all())


def get_role_ids_of_user(session: Session, uid: int) -> List[int]:
    urs = session.exec(select(UserRole).where(UserRole.user_id == uid)).all()
    return [ur.role_id for ur in urs]


def create_role(session: Session, data: RoleCreate) -> Tuple[Optional[Role], str]:
    try:
        existing = session.exec(select(Role).where(Role.code == data.code)).first()
        if existing:
            return None, f"Mã vai trò '{data.code}' đã tồn tại"

        role = Role(
            code=data.code.strip().upper(),
            name=data.name.strip(),
            description=data.description,
        )
        session.add(role)
        session.flush()

        for pid in data.permission_ids:
            if session.get(Permission, pid):
                session.add(RolePermission(role_id=role.id, permission_id=pid))

        session.commit()
        session.refresh(role)
        return role, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo vai trò: {e}"


def update_role(
    session: Session, rid: int, data: RoleUpdate,
) -> Tuple[Optional[Role], str]:
    try:
        role = session.get(Role, rid)
        if not role:
            return None, "Vai trò không tồn tại"

        role.name = data.name.strip()
        role.description = data.description
        session.add(role)

        # Xóa permissions cũ
        old_rps = session.exec(
            select(RolePermission).where(RolePermission.role_id == rid)
        ).all()
        for rp in old_rps:
            session.delete(rp)
        session.flush()

        # Thêm permissions mới
        for pid in data.permission_ids:
            if session.get(Permission, pid):
                session.add(RolePermission(role_id=rid, permission_id=pid))

        session.commit()
        session.refresh(role)
        return role, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi cập nhật: {e}"


def delete_role(session: Session, rid: int) -> Tuple[bool, str]:
    role = session.get(Role, rid)
    if not role:
        return False, "Vai trò không tồn tại"
    if role.is_system:
        return False, "Không thể xóa vai trò hệ thống"

    # Kiểm tra có user dùng không
    in_use = session.exec(
        select(UserRole).where(UserRole.role_id == rid)
    ).first()
    if in_use:
        return False, "Không thể xóa: Có user đang dùng vai trò này"

    # Xóa RolePermissions
    rps = session.exec(
        select(RolePermission).where(RolePermission.role_id == rid)
    ).all()
    for rp in rps:
        session.delete(rp)

    session.delete(role)
    session.commit()
    return True, "Đã xóa vai trò"


# ============================================================
# PERMISSION
# ============================================================
def get_all_permissions(session: Session) -> List[Permission]:
    return list(session.exec(
        select(Permission).order_by(Permission.module, Permission.order_index)
    ).all())


def get_permissions_by_module(session: Session) -> dict:
    """Group permissions theo module để dễ hiển thị UI."""
    perms = get_all_permissions(session)
    grouped = {}
    for p in perms:
        grouped.setdefault(p.module, []).append(p)
    return grouped


def get_permission_ids_of_role(session: Session, rid: int) -> List[int]:
    rps = session.exec(
        select(RolePermission).where(RolePermission.role_id == rid)
    ).all()
    return [rp.permission_id for rp in rps]


def get_permission_codes_of_user(session: Session, uid: int) -> List[str]:
    """Lấy tất cả permission code của user (union từ các roles)."""
    stmt = (
        select(Permission.code)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == uid)
    )
    return list(set(session.exec(stmt).all()))


def has_permission(session: Session, uid: int, code: str) -> bool:
    """Check user có quyền cụ thể không."""
    codes = get_permission_codes_of_user(session, uid)
    return code in codes


def is_admin(session: Session, uid: int) -> bool:
    """Check user có role ADMIN không."""
    roles = get_roles_of_user(session, uid)
    return any(r.code == "ADMIN" for r in roles)


# ============================================================
# AUDIT LOG
# ============================================================
def write_audit(
    session: Session, user_id: Optional[int], action: str,
    model: str = "", record_id: Optional[int] = None,
    old_value: dict = None, new_value: dict = None,
    description: str = "", ip: str = "", user_agent: str = "",
):
    """Ghi audit log. Không commit (để caller commit chung)."""
    try:
        username = ""
        if user_id:
            u = session.get(User, user_id)
            if u:
                username = u.username

        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            model=model,
            record_id=record_id,
            description=description,
            old_value=json.dumps(old_value, ensure_ascii=False, default=str) if old_value else "",
            new_value=json.dumps(new_value, ensure_ascii=False, default=str) if new_value else "",
            ip_address=ip,
            user_agent=user_agent[:300] if user_agent else "",
        )
        session.add(log)
    except Exception as e:
        print(f"[WARN] Không ghi được audit: {e}")


def get_audit_logs(
    session: Session,
    keyword: str = "",
    action: str = "",
    model: str = "",
    date_from=None, date_to=None,
    limit: int = 500,
) -> List[AuditLog]:
    stmt = select(AuditLog)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(or_(
            AuditLog.username.like(p),
            AuditLog.description.like(p),
        ))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if model:
        stmt = stmt.where(AuditLog.model == model)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(
            date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(
            date_to, datetime.max.time(), tzinfo=timezone.utc))
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


# ============================================================
# SEED DATA (chạy 1 lần khi khởi động)
# ============================================================
# Danh sách permissions toàn hệ thống
SEED_PERMISSIONS = [
    # === INVENTORY (Kho) ===
    ("inventory.product.view", "Xem sản phẩm", "inventory", "view"),
    ("inventory.product.create", "Tạo sản phẩm", "inventory", "create"),
    ("inventory.product.edit", "Sửa sản phẩm", "inventory", "edit"),
    ("inventory.product.delete", "Xóa sản phẩm", "inventory", "delete"),
    ("inventory.category.manage", "Quản lý danh mục", "inventory", "edit"),
    ("inventory.supplier.manage", "Quản lý NCC", "inventory", "edit"),
    ("inventory.stock_move.view", "Xem nhập/xuất kho", "inventory", "view"),
    ("inventory.stock_move.create", "Tạo phiếu nhập/xuất", "inventory", "create"),
    ("inventory.stock_move.delete", "Xóa phiếu nhập/xuất", "inventory", "delete"),
    ("inventory.stock_move.force_delete", "Force delete phiếu", "inventory", "delete"),

    # === SALES (Bán hàng) ===
    ("sales.customer.view", "Xem khách hàng", "sales", "view"),
    ("sales.customer.manage", "Quản lý khách hàng", "sales", "edit"),
    ("sales.pos.use", "Dùng POS bán hàng", "sales", "other"),
    ("sales.order.view", "Xem đơn bán", "sales", "view"),
    ("sales.order.create", "Tạo đơn bán", "sales", "create"),
    ("sales.order.edit", "Sửa đơn bán", "sales", "edit"),
    ("sales.order.delete", "Xóa đơn bán", "sales", "delete"),
    ("sales.return.view", "Xem phiếu trả hàng", "sales", "view"),
    ("sales.return.create", "Tạo phiếu trả hàng", "sales", "create"),
    ("sales.discount.manage", "Quản lý mã giảm giá", "sales", "edit"),
    ("sales.shift.view", "Xem ca làm việc", "sales", "view"),
    ("sales.shift.open", "Mở ca", "sales", "other"),
    ("sales.shift.close", "Đóng ca", "sales", "other"),
    ("sales.shift.view_revenue", "Xem doanh thu ca", "sales", "view"),
    ("sales.report.view", "Xem báo cáo bán hàng", "sales", "view"),

    # === PURCHASE (Mua hàng) ===
    ("purchase.order.view", "Xem đơn mua", "purchase", "view"),
    ("purchase.order.create", "Tạo đơn mua", "purchase", "create"),
    ("purchase.order.edit", "Sửa đơn mua", "purchase", "edit"),
    ("purchase.order.delete", "Xóa đơn mua", "purchase", "delete"),
    ("purchase.order.approve", "Duyệt đơn mua", "purchase", "approve"),
    ("purchase.receive.create", "Nhận hàng & nhập kho", "purchase", "create"),
    ("purchase.return.view", "Xem phiếu trả NCC", "purchase", "view"),
    ("purchase.return.create", "Tạo phiếu trả NCC", "purchase", "create"),
    ("purchase.return.approve", "Duyệt phiếu trả NCC", "purchase", "approve"),
    ("purchase.debt.view", "Xem công nợ NCC", "purchase", "view"),

    # === ACCOUNTING (Kế toán) ===
    ("accounting.settings.edit", "Sửa cấu hình kế toán", "accounting", "edit"),
    ("accounting.cash_account.manage", "Quản lý tài khoản quỹ", "accounting", "edit"),
    ("accounting.voucher.view", "Xem phiếu thu/chi", "accounting", "view"),
    ("accounting.voucher.create", "Tạo phiếu thu/chi", "accounting", "create"),
    ("accounting.voucher.delete", "Xóa phiếu thu/chi", "accounting", "delete"),
    ("accounting.asset.view", "Xem tài sản", "accounting", "view"),
    ("accounting.asset.manage", "Quản lý tài sản", "accounting", "edit"),
    ("accounting.depreciation.run", "Chạy khấu hao", "accounting", "other"),
    ("accounting.period.lock", "Khóa kỳ kế toán", "accounting", "other"),
    ("accounting.report.view", "Xem báo cáo kế toán", "accounting", "view"),
    ("accounting.tax.view", "Xem báo cáo thuế", "accounting", "view"),

    # === AUTH (Người dùng) ===
    ("auth.user.view", "Xem người dùng", "auth", "view"),
    ("auth.user.manage", "Quản lý người dùng", "auth", "edit"),
    ("auth.role.view", "Xem vai trò", "auth", "view"),
    ("auth.role.manage", "Quản lý vai trò", "auth", "edit"),
    ("auth.audit.view", "Xem lịch sử thao tác", "auth", "view"),

    # === INTERNAL (Nội bộ) ===
    ("internal.post.view", "Xem bài viết nội bộ", "internal", "view"),
    ("internal.post.create", "Tạo bài viết", "internal", "create"),
    ("internal.post.edit", "Sửa bài viết", "internal", "edit"),
    ("internal.post.delete", "Xóa bài viết", "internal", "delete"),
    ("internal.category.manage", "Quản lý danh mục nội bộ", "internal", "edit"),
    ("internal.category.view", "Xem danh mục nội bộ", "internal", "view"),
]


SEED_ROLES = [
    ("ADMIN", "Quản trị viên", "Toàn quyền hệ thống", True),
    ("KETOAN", "Kế toán", "Quản lý kế toán, duyệt đơn, khóa kỳ", True),
    ("BANHANG", "Bán hàng", "Bán hàng POS, quản lý khách hàng", True),
    ("THUKHO", "Thủ kho", "Quản lý kho, nhập xuất hàng", True),
    ("MUAHANG", "Mua hàng", "Đặt hàng NCC, nhận hàng", True),
    ("CHIXEM", "Chỉ xem", "Chỉ xem báo cáo, không sửa", True),
]


def seed_data(session: Session):
    """Tạo permissions + roles + admin mặc định. Idempotent — chạy nhiều lần không lỗi."""
    # 1. Tạo Permissions
    for code, name, module, action in SEED_PERMISSIONS:
        existing = session.exec(
            select(Permission).where(Permission.code == code)
        ).first()
        if not existing:
            session.add(Permission(
                code=code, name=name, module=module, action=action,
                order_index=len(session.exec(select(Permission)).all()),
            ))
    session.commit()

    # 2. Tạo Roles
    for code, name, desc, is_sys in SEED_ROLES:
        existing = session.exec(select(Role).where(Role.code == code)).first()
        if not existing:
            session.add(Role(
                code=code, name=name, description=desc, is_system=is_sys,
            ))
    session.commit()

    # 3. Gán permissions cho roles
    all_perms = session.exec(select(Permission)).all()
    perm_by_code = {p.code: p.id for p in all_perms}
    role_by_code = {r.code: r.id for r in session.exec(select(Role)).all()}

    role_perm_map = _build_role_permission_map(perm_by_code)

    for role_code, perm_codes in role_perm_map.items():
        rid = role_by_code.get(role_code)
        if not rid:
            continue
        for perm_code in perm_codes:
            pid = perm_by_code.get(perm_code)
            if not pid:
                continue
            existing = session.exec(
                select(RolePermission)
                .where(RolePermission.role_id == rid)
                .where(RolePermission.permission_id == pid)
            ).first()
            if not existing:
                session.add(RolePermission(role_id=rid, permission_id=pid))
    session.commit()

    # 4. Tạo admin mặc định
    admin = session.exec(select(User).where(User.username == "admin")).first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=hash_password("admin"),
            full_name="Quản trị viên",
            email="",
            phone="",
            status="ACTIVE",
            must_change_password=True,
        )
        session.add(admin)
        session.flush()

        # Gán role ADMIN
        admin_role_id = role_by_code.get("ADMIN")
        if admin_role_id:
            session.add(UserRole(user_id=admin.id, role_id=admin_role_id))
        session.commit()
        print("✅ Đã tạo tài khoản admin/admin — Vui lòng đổi mật khẩu sau khi đăng nhập lần đầu.")
    # 5. Seed danh mục Nội bộ mặc định
    from app.modules.noi_bo.models import InternalCategory
    default_cats = [
        ("NHATKY_CA", "Nhật ký ca", "Ghi chú ca làm việc hàng ngày", "#0dcaf0", "bi-journal-text", 1, False),
        ("BANGIAO_CA", "Bàn giao ca", "Bàn giao thông tin cho ca sau", "#ffc107", "bi-arrow-left-right", 2, False),
        ("NOIQUY", "Nội quy", "Quy định, nội quy cửa hàng", "#dc3545", "bi-shield-exclamation", 3, True),
        ("THONGBAO", "Thông báo", "Thông báo từ quản lý", "#0d6efd", "bi-megaphone", 4, False),
        ("QUYTRINH", "Quy trình", "Hướng dẫn thao tác nghiệp vụ", "#198754", "bi-list-check", 5, False),
    ]
    for code, name, desc, color, icon, order, req_read in default_cats:
        existing = session.exec(
            select(InternalCategory).where(InternalCategory.code == code)
        ).first()
        if not existing:
            session.add(InternalCategory(
                code=code, name=name, description=desc,
                color=color, icon=icon, order_index=order,
                is_require_read=req_read, is_system=True,
            ))
    session.commit()
    print("✅ Đã seed 5 danh mục Nội bộ mặc định")


def _build_role_permission_map(perm_by_code: dict) -> dict:
    """Định nghĩa permissions cho từng role."""

    # ADMIN: tất cả
    all_codes = list(perm_by_code.keys())

    # KETOAN: kế toán + xem toàn bộ + duyệt
    ketoan = [
        # Xem tất cả
        *[c for c in all_codes if c.endswith(".view")],
        # Kế toán
        "accounting.settings.edit",
        "accounting.cash_account.manage",
        "accounting.voucher.create",
        "accounting.asset.manage",
        "accounting.depreciation.run",
        "accounting.period.lock",
        # Duyệt
        "purchase.order.approve",
        "purchase.return.approve",
        # Xem doanh thu ca
        "sales.shift.view_revenue",
    ]

    # BANHANG: bán hàng + xem sản phẩm
    banhang = [
        "inventory.product.view",
        "inventory.stock_move.view",
        "sales.customer.view",
        "sales.customer.manage",
        "sales.pos.use",
        "sales.order.view",
        "sales.order.create",
        "sales.order.edit",
        "sales.return.view",
        "sales.return.create",
        "sales.shift.view",
        "sales.shift.open",
        "sales.shift.close",
        "sales.report.view",
    ]

    # THUKHO: kho
    thukho = [
        "inventory.product.view",
        "inventory.product.create",
        "inventory.product.edit",
        "inventory.category.manage",
        "inventory.supplier.manage",
        "inventory.stock_move.view",
        "inventory.stock_move.create",
        "purchase.order.view",
        "purchase.receive.create",
        "purchase.return.view",
        "purchase.return.create",
    ]

    # MUAHANG: mua hàng
    muahang = [
        "inventory.product.view",
        "inventory.supplier.manage",
        "purchase.order.view",
        "purchase.order.create",
        "purchase.order.edit",
        "purchase.receive.create",
        "purchase.return.view",
        "purchase.return.create",
        "purchase.debt.view",
    ]

    # CHIXEM: chỉ xem toàn bộ
    chixem = [c for c in all_codes if c.endswith(".view")]

    return {
        "ADMIN": all_codes,
        "KETOAN": list(set(ketoan)),
        "BANHANG": list(set(banhang)),
        "THUKHO": list(set(thukho)),
        "MUAHANG": list(set(muahang)),
        "CHIXEM": list(set(chixem)),
    }