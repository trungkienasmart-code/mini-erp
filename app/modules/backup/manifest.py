MANIFEST = {
    "name": "Sao lưu & Phục hồi",
    "version": "1.0.0",
    "summary": "Backup dữ liệu, phục hồi, export Excel",
    "depends": ["auth"],
    "author": "Tên bạn",
    "category": "System",
    "icon": "bi-cloud-arrow-down-fill",
    "url_prefix": "/backup",
    "menus": [
        {"name": "Sao lưu & Phục hồi", "url": "/backup/", "icon": "bi-hdd"},
        {"name": "Xuất dữ liệu Excel", "url": "/backup/export", "icon": "bi-file-earmark-excel"},
    ],
}