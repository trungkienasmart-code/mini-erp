MANIFEST = {
    "name": "Kế Toán",
    "version": "1.0.0",
    "summary": "Kế toán hộ kinh doanh theo TT152/2025/TT-BTC",
    "depends": ["quan_ly_kho", "ban_hang", "mua_hang"],
    "author": "Tên bạn",
    "category": "Accounting",
    "icon": "bi-calculator",
    "url_prefix": "/accounting",
    "menus": [
        {"name": "Tổng quan", "url": "/accounting/", "icon": "bi-speedometer2"},
        {"name": "Cấu hình HKD", "url": "/accounting/settings", "icon": "bi-gear"},
        {"name": "Tài khoản quỹ", "url": "/accounting/cash-accounts", "icon": "bi-wallet2"},
        {"name": "Phiếu thu/chi", "url": "/accounting/vouchers", "icon": "bi-receipt-cutoff"},
        {"name": "Tài sản cố định", "url": "/accounting/assets", "icon": "bi-building"},
        {"name": "Báo cáo sổ sách", "url": "/accounting/reports", "icon": "bi-file-earmark-bar-graph"},
    ],
}