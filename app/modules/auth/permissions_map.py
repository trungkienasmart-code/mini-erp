# app/modules/auth/permissions_map.py
"""
Bảng mapping URL path → permission cần có.
Dùng để middleware chặn truy cập trái phép khi gõ tay URL.
"""

# Danh sách (path_prefix, required_permission).
# - required_permission = None → KHÔNG cần quyền (ai cũng dùng được)
# - Ưu tiên prefix DÀI hơn (đã sắp xếp tự động khi load)
_ROUTE_MAP = [
    # === INVENTORY (Kho) ===
    ("/inventory/api", None),  # API nội bộ, không cần quyền
    ("/inventory/products/new", "inventory.product.create"),
    ("/inventory/products/", "inventory.product.view"),  # edit, detail
    ("/inventory/products", "inventory.product.view"),
    ("/inventory/categories", "inventory.category.manage"),
    ("/inventory/suppliers", "inventory.supplier.manage"),
    ("/inventory/stock-moves", "inventory.stock_move.view"),
    ("/inventory/uoms", "inventory.product.edit"),
    ("/inventory/barcodes", "inventory.product.edit"),

    # === SALES (Bán hàng) ===
    ("/sales/api", None),
    ("/sales/pos", "sales.pos.use"),
    ("/sales/orders/new", "sales.order.create"),
    ("/sales/orders/export", "sales.order.view"),
    ("/sales/orders/", "sales.order.view"),
    ("/sales/orders", "sales.order.view"),
    ("/sales/customers", "sales.customer.view"),
    ("/sales/discounts", "sales.discount.manage"),
    ("/sales/returns", "sales.return.view"),
    ("/sales/shifts", "sales.shift.view"),
    ("/sales/reports", "sales.report.view"),
    ("/sales", "sales.order.view"),

    # === PURCHASE (Mua hàng) ===
    ("/purchase/api", None),
    ("/purchase/receives/new", "purchase.receive.create"),
    ("/purchase/receives/export", "purchase.receive.create"),
    ("/purchase/receives", "purchase.receive.create"),
    ("/purchase/orders/new", "purchase.order.create"),
    ("/purchase/orders/export", "purchase.order.view"),
    ("/purchase/orders/", "purchase.order.view"),
    ("/purchase/orders", "purchase.order.view"),
    ("/purchase/returns/new", "purchase.return.create"),
    ("/purchase/returns/", "purchase.return.view"),
    ("/purchase/returns", "purchase.return.view"),
    ("/purchase/supplier-debt", "purchase.debt.view"),
    ("/purchase", "purchase.order.view"),

    # === ACCOUNTING (Kế toán) ===
    ("/accounting/settings", "accounting.settings.edit"),
    ("/accounting/cash-accounts", "accounting.cash_account.manage"),
    ("/accounting/vouchers/new", "accounting.voucher.create"),
    ("/accounting/vouchers/export", "accounting.voucher.view"),
    ("/accounting/vouchers/", "accounting.voucher.view"),
    ("/accounting/vouchers", "accounting.voucher.view"),
    ("/accounting/assets/new", "accounting.asset.manage"),
    ("/accounting/assets/", "accounting.asset.view"),
    ("/accounting/assets", "accounting.asset.view"),
    ("/accounting/depreciation", "accounting.depreciation.run"),
    ("/accounting/periods", "accounting.period.lock"),
    ("/accounting/reports/tax", "accounting.tax.view"),
    ("/accounting/reports/debt", "accounting.report.view"),
    ("/accounting/reports/", "accounting.report.view"),
    ("/accounting/reports", "accounting.report.view"),
    ("/accounting", "accounting.report.view"),

    # === AUTH (Người dùng) ===
    ("/auth/users/new", "auth.user.manage"),
    ("/auth/users/", "auth.user.manage"),
    ("/auth/users", "auth.user.view"),
    ("/auth/roles/new", "auth.role.manage"),
    ("/auth/roles/", "auth.role.manage"),
    ("/auth/roles", "auth.role.view"),
    ("/auth/audit-log", "auth.audit.view"),
    ("/auth/profile", None),  # Ai cũng dùng
    ("/auth/login", None),
    ("/auth/logout", None),

    # === INTERNAL (Nội bộ) ===
    ("/internal/api", None),
    ("/internal/categories/new", "internal.category.manage"),
    ("/internal/categories/", "internal.category.manage"),
    ("/internal/categories", "internal.post.view"),
    ("/internal/posts/new", "internal.post.create"),
    ("/internal/posts/", "internal.post.view"),
    ("/internal/posts", "internal.post.view"),
    ("/internal/attachments/", None),  # Download file — check riêng
    ("/internal", "internal.post.view"),
]

# Sắp xếp theo độ dài prefix giảm dần (match cái cụ thể trước)
_ROUTE_MAP_SORTED = sorted(_ROUTE_MAP, key=lambda x: -len(x[0]))


def find_required_permission(path: str) -> tuple:
    """
    Tìm permission cần có cho path.
    Trả về (found: bool, permission: Optional[str]).
    - (False, None): Path không nằm trong danh sách quản lý → cho qua.
    - (True, None): Path không cần quyền → cho qua.
    - (True, "xxx"): Path cần quyền "xxx".
    """
    for prefix, perm in _ROUTE_MAP_SORTED:
        if path.startswith(prefix):
            return True, perm
    return False, None