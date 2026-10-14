MANIFEST = {
    "name": "Nhập liệu",
    "version": "1.0.0",
    "summary": "Import Excel cho sản phẩm, NCC, đơn mua",
    "depends": ["auth", "quan_ly_kho", "mua_hang"],
    "author": "Tên bạn",
    "category": "System",
    "icon": "bi-upload",
    "url_prefix": "/import",
    "menus": [
        {"name": "Import Excel", "url": "/import/", "icon": "bi-file-earmark-arrow-up"},
    ],
}