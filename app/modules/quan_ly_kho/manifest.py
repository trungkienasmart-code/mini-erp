MANIFEST = {
    "name": "Quản Lý Kho",
    "version": "1.0.0",
    "summary": "Quản lý danh mục và sản phẩm",
    "depends": [],
    "author": "Tên bạn",
    "category": "Inventory",
    "icon": "bi-box-seam",
    "url_prefix": "/inventory",
    "menus": [
        {"name": "Sản phẩm", "url": "/inventory/products", "icon": "bi-box"},
        {"name": "Danh mục", "url": "/inventory/categories", "icon": "bi-tags"},
        {"name": "Nhà cung cấp", "url": "/inventory/suppliers", "icon": "bi-truck"},
        {"name": "Nhập/Xuất kho", "url": "/inventory/stock-moves", "icon": "bi-arrow-left-right"},
    ],
}