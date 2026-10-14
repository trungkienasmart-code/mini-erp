MANIFEST = {
    "name": "Cài đặt",
    "version": "1.0.0",
    "summary": "Cấu hình cửa hàng, mạng LAN, ngân hàng, backup",
    "depends": ["auth", "ke_toan"],
    "author": "Tên bạn",
    "category": "System",
    "icon": "bi-gear-fill",
    "url_prefix": "/settings",
    "menus": [
        {"name": "Thông tin cửa hàng", "url": "/settings/", "icon": "bi-shop"},
        {"name": "Mạng LAN", "url": "/settings/network", "icon": "bi-wifi"},
        {"name": "Ngân hàng & VietQR", "url": "/settings/bank", "icon": "bi-bank"},
    ],
}