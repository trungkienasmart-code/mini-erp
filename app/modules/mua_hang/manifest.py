MANIFEST = {
    "name": "Mua Hàng",
    "version": "1.0.0",
    "summary": "Đặt hàng NCC, nhập kho, công nợ phải trả",
    "depends": ["quan_ly_kho"],
    "author": "Tên bạn",
    "category": "Purchase",
    "icon": "bi-cart-plus-fill",
    "url_prefix": "/purchase",
    "menus": [
        {"name": "Dashboard", "url": "/purchase/", "icon": "bi-speedometer2"},
        {"name": "Đơn mua hàng", "url": "/purchase/orders", "icon": "bi-file-text"},
        {"name": "Nhập kho", "url": "/purchase/receives", "icon": "bi-box-arrow-in-down"},
        {"name": "Trả hàng NCC", "url": "/purchase/returns", "icon": "bi-arrow-return-right"},
        {"name": "Công nợ NCC", "url": "/purchase/supplier-debt", "icon": "bi-cash-coin"},
    ],
}
