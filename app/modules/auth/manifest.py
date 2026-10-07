MANIFEST = {
    "name": "Người dùng",
    "version": "1.0.0",
    "summary": "Quản lý người dùng, vai trò, phân quyền, audit log",
    "depends": [],  # Không phụ thuộc module nào
    "author": "Tên bạn",
    "category": "System",
    "icon": "bi-people-fill",
    "url_prefix": "/auth",
    "menus": [
        {"name": "Người dùng", "url": "/auth/users", "icon": "bi-person-badge"},
        {"name": "Vai trò", "url": "/auth/roles", "icon": "bi-shield-check"},
        {"name": "Lịch sử thao tác", "url": "/auth/audit-log", "icon": "bi-clock-history"},
    ],
}