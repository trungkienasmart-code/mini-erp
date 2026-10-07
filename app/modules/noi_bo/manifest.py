MANIFEST = {
    "name": "Nội bộ",
    "version": "1.0.0",
    "summary": "Nhật ký ca, bàn giao, nội quy, thông báo",
    "depends": ["auth"],
    "author": "Tên bạn",
    "category": "Internal",
    "icon": "bi-journal-bookmark-fill",
    "url_prefix": "/internal",
    "menus": [
        {"name": "Bảng tin", "url": "/internal/", "icon": "bi-newspaper"},
        {"name": "Danh mục", "url": "/internal/categories", "icon": "bi-tags"},
    ],
}