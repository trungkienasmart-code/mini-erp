# app/modules/nhap_lieu/services.py
import io
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlmodel import Session, select, or_


# ============================================================
# CONSTANTS
# ============================================================
MAX_ROWS = 1000
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Header cho template sản phẩm
PRODUCT_HEADERS = [
    "Mã SKU", "Tên sản phẩm", "Ngành hàng", "Nhà cung cấp",
    "ĐVT", "Giá nhập", "Giá bán", "VAT (%)",
    "Tồn tối thiểu", "Phương pháp giá vốn",
]

# Header cho template NCC (Buổi 3B)
SUPPLIER_HEADERS = [
    "Mã NCC", "Tên NCC", "SĐT", "Email",
    "Địa chỉ", "Mã số thuế", "Số ngày nợ",
]


# ============================================================
# STYLE HELPERS
# ============================================================
def _apply_header_style(ws, headers: list, color: str = "0d6efd"):
    """Áp dụng style cho hàng header."""
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_fill = PatternFill("solid", fgColor=color)
    header_align = Alignment(horizontal="center", vertical="center")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border

    ws.row_dimensions[1].height = 25


def _apply_data_style(ws, num_rows: int, num_cols: int):
    """Áp dụng border + alignment cho vùng dữ liệu."""
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )
    for row in range(2, num_rows + 2):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = border
            cell.alignment = Alignment(vertical="center")


def _auto_width(ws, headers: list, min_width: int = 12):
    """Tự động set độ rộng cột theo header."""
    for col, h in enumerate(headers, 1):
        width = max(len(str(h)) + 4, min_width)
        ws.column_dimensions[get_column_letter(col)].width = width


# ============================================================
# TEMPLATE GENERATION
# ============================================================
def generate_products_template() -> bytes:
    """Tạo file Excel template cho import sản phẩm."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sản phẩm"

    _apply_header_style(ws, PRODUCT_HEADERS, color="0d6efd")

    # Sample data (2 dòng ví dụ)
    samples = [
        ["COCA-LON", "Nước ngọt Coca 330ml", "Nước giải khát", "NCC001",
         "Lon", 8000, 12000, 10, 20, "FIFO"],
        ["PEPSI-500", "Pepsi 500ml", "Nước giải khát", "",
         "Chai", 7000, 10000, 10, 10, "FIFO"],
    ]
    for row_data in samples:
        ws.append(row_data)

    _apply_data_style(ws, len(samples), len(PRODUCT_HEADERS))
    _auto_width(ws, PRODUCT_HEADERS)

    # Data validation cho "Phương pháp giá vốn"
    dv_cost_method = DataValidation(
        type="list",
        formula1='"FIFO,LIFO"',
        allow_blank=True,
    )
    dv_cost_method.error = "Chỉ chấp nhận FIFO hoặc LIFO"
    dv_cost_method.errorTitle = "Giá trị không hợp lệ"
    ws.add_data_validation(dv_cost_method)
    dv_cost_method.add(f"J2:J{MAX_ROWS + 1}")

    # Ghi chú sheet
    note_ws = wb.create_sheet("Hướng dẫn")
    note_ws.column_dimensions['A'].width = 100
    notes = [
        ("HƯỚNG DẪN IMPORT SẢN PHẨM", True),
        ("", False),
        ("1. Điền dữ liệu vào sheet 'Sản phẩm'.", False),
        ("2. Cột 'Mã SKU' là BẮT BUỘC. Dùng làm khóa chính để nhận diện sản phẩm.", False),
        ("3. Nếu Mã SKU đã tồn tại → hệ thống CẬP NHẬT. Nếu chưa → TẠO MỚI.", False),
        ("4. Cột 'Ngành hàng' - nếu chưa tồn tại, hệ thống tự tạo mới.", False),
        ("5. Cột 'Nhà cung cấp' - nhập Mã NCC (VD: NCC001). Để trống nếu chưa có.", False),
        ("6. Cột 'Giá nhập', 'Giá bán' - nhập số, không có dấu chấm phẩy.", False),
        ("7. Cột 'VAT (%)' - nhập số từ 0 đến 100. VD: 10 cho VAT 10%.", False),
        ("8. Cột 'Phương pháp giá vốn' - chọn FIFO hoặc LIFO (dropdown).", False),
        ("9. Tồn kho KHÔNG được import. Dùng phiếu nhập kho để tăng tồn.", False),
        ("10. Tối đa 1,000 dòng/lần import.", False),
        ("", False),
        ("⚠️ LƯU Ý: Xóa 2 dòng ví dụ trước khi import dữ liệu thật.", False),
    ]
    for idx, (text, bold) in enumerate(notes, 1):
        cell = note_ws.cell(row=idx, column=1, value=text)
        if bold:
            cell.font = Font(bold=True, size=14, color="0d6efd")

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def generate_suppliers_template() -> bytes:
    """Tạo file Excel template cho import NCC."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Nhà cung cấp"

    _apply_header_style(ws, SUPPLIER_HEADERS, color="dc3545")

    samples = [
        ["NCC001", "Công ty TNHH Coca-Cola VN", "0941396688",
         "contact@coca.vn", "123 Lê Lợi, Q1, TP.HCM", "0123456789", 30],
        ["NCC002", "Công ty Pepsi VN", "0912345678",
         "info@pepsi.vn", "456 Nguyễn Huệ, Q1", "9876543210", 15],
    ]
    for row_data in samples:
        ws.append(row_data)

    _apply_data_style(ws, len(samples), len(SUPPLIER_HEADERS))
    _auto_width(ws, SUPPLIER_HEADERS)

    note_ws = wb.create_sheet("Hướng dẫn")
    note_ws.column_dimensions['A'].width = 100
    notes = [
        ("HƯỚNG DẪN IMPORT NHÀ CUNG CẤP", True),
        ("", False),
        ("1. Cột 'Mã NCC' là BẮT BUỘC.", False),
        ("2. Nếu Mã NCC đã tồn tại → CẬP NHẬT. Chưa → TẠO MỚI.", False),
        ("3. 'Số ngày nợ' là số ngày được nợ khi mua hàng.", False),
        ("4. Tối đa 1,000 dòng/lần import.", False),
        ("", False),
        ("⚠️ LƯU Ý: Xóa 2 dòng ví dụ trước khi import dữ liệu thật.", False),
    ]
    for idx, (text, bold) in enumerate(notes, 1):
        cell = note_ws.cell(row=idx, column=1, value=text)
        if bold:
            cell.font = Font(bold=True, size=14, color="dc3545")

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# ============================================================
# PARSE EXCEL
# ============================================================
def parse_excel(file_content: bytes, expected_headers: list) -> Tuple[List[dict], str]:
    """
    Đọc file Excel → list of dicts.
    Skip 2 dòng đầu nếu là sample data (nếu user chưa xóa).
    """
    try:
        wb = load_workbook(io.BytesIO(file_content), data_only=True)
        ws = wb.active

        # Đọc header
        header_row = [cell.value for cell in ws[1] if cell.value]
        if not header_row:
            return [], "File Excel trống hoặc thiếu header"

        # Map header → index
        header_map = {}
        for idx, h in enumerate(header_row):
            h_str = str(h).strip()
            if h_str in expected_headers:
                header_map[h_str] = idx

        # Kiểm tra header bắt buộc
        missing = [h for h in expected_headers if h not in header_map]
        if len(missing) > len(expected_headers) // 2:
            return [], f"File thiếu quá nhiều cột. Cần các cột: {', '.join(expected_headers[:3])}..."

        # Đọc data
        rows = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            # Skip dòng trống
            if not any(cell for cell in row):
                continue

            row_dict = {"_row": row_idx}
            for header, col_idx in header_map.items():
                if col_idx < len(row):
                    val = row[col_idx]
                    row_dict[header] = val
                else:
                    row_dict[header] = None

            rows.append(row_dict)

        # Giới hạn
        if len(rows) > MAX_ROWS:
            return [], f"File có {len(rows)} dòng, vượt quá giới hạn {MAX_ROWS} dòng/lần"

        return rows, "OK"

    except Exception as e:
        return [], f"Lỗi đọc file Excel: {e}"


# ============================================================
# VALIDATE — SẢN PHẨM
# ============================================================
def validate_products(session: Session, rows: List[dict]) -> Tuple[List[dict], dict]:
    """
    Validate từng dòng import sản phẩm.
    Trả về: (list results, summary dict)
    """
    from app.modules.quan_ly_kho.models import Product, Category, Supplier

    results = []
    summary = {"total": len(rows), "create": 0, "update_count": 0, "error": 0}

    # Cache danh mục + NCC để check nhanh
    existing_cats = {c.name.lower(): c for c in session.exec(select(Category)).all()}
    existing_sups = {s.code.upper(): s for s in session.exec(select(Supplier)).all()}

    for row in rows:
        row_num = row.get("_row", 0)
        errors = []

        # === SKU ===
        sku = row.get("Mã SKU")
        sku = str(sku).strip() if sku else ""
        if not sku:
            errors.append("Thiếu Mã SKU")
        elif len(sku) > 50:
            errors.append(f"Mã SKU quá dài (>{50} ký tự)")

        # === Tên SP ===
        name = row.get("Tên sản phẩm")
        name = str(name).strip() if name else ""
        if not name:
            errors.append("Thiếu Tên sản phẩm")
        elif len(name) > 200:
            errors.append(f"Tên quá dài (>{200} ký tự)")

        # === Ngành hàng ===
        cat_name = row.get("Ngành hàng")
        cat_name = str(cat_name).strip() if cat_name else ""

        # === NCC ===
        sup_code = row.get("Nhà cung cấp")
        sup_code = str(sup_code).strip().upper() if sup_code else ""
        sup_obj = existing_sups.get(sup_code) if sup_code else None
        if sup_code and not sup_obj:
            errors.append(f"NCC '{sup_code}' không tồn tại (sẽ để trống)")

        # === ĐVT ===
        unit = row.get("ĐVT")
        unit = str(unit).strip() if unit else "Cái"
        if len(unit) > 20:
            errors.append(f"ĐVT quá dài (>{20} ký tự)")

        # === Giá nhập ===
        try:
            cost_price = float(row.get("Giá nhập") or 0)
            if cost_price < 0:
                errors.append("Giá nhập < 0")
        except (ValueError, TypeError):
            cost_price = 0
            errors.append("Giá nhập không hợp lệ")

        # === Giá bán ===
        try:
            price = float(row.get("Giá bán") or 0)
            if price < 0:
                errors.append("Giá bán < 0")
        except (ValueError, TypeError):
            price = 0
            errors.append("Giá bán không hợp lệ")

        # === VAT ===
        try:
            tax_rate = float(row.get("VAT (%)") or 0)
            if tax_rate < 0 or tax_rate > 100:
                errors.append("VAT phải từ 0-100")
        except (ValueError, TypeError):
            tax_rate = 0
            errors.append("VAT không hợp lệ")

        # === Tồn tối thiểu ===
        try:
            min_stock = int(row.get("Tồn tối thiểu") or 0)
            if min_stock < 0:
                errors.append("Tồn tối thiểu < 0")
        except (ValueError, TypeError):
            min_stock = 0
            errors.append("Tồn tối thiểu không hợp lệ")

        # === Phương pháp giá vốn ===
        cost_method = str(row.get("Phương pháp giá vốn") or "FIFO").strip().upper()
        if cost_method not in ("FIFO", "LIFO"):
            errors.append(f"Phương pháp '{cost_method}' không hợp lệ (chỉ FIFO/LIFO)")
            cost_method = "FIFO"

        # === Xác định CREATE/UPDATE ===
        action = ""
        existing_product = None
        if sku and not errors:
            existing_product = session.exec(
                select(Product).where(Product.sku == sku)
            ).first()
            if existing_product:
                action = "UPDATE"
                summary["update_count"] += 1
            else:
                action = "CREATE"
                summary["create"] += 1

        if errors:
            action = "ERROR"
            summary["error"] += 1

        # Chuẩn hóa data để hiển thị
        results.append({
            "row_num": row_num,
            "sku": sku or "—",
            "name": name or "—",
            "category_name": cat_name or "—",
            "supplier_code": sup_code or "—",
            "unit": unit,
            "cost_price": cost_price,
            "price": price,
            "tax_rate": tax_rate,
            "min_stock": min_stock,
            "cost_method": cost_method,
            "action": action,
            "errors": errors,
            "_raw": row,
        })

    return results, summary


# ============================================================
# EXECUTE IMPORT — SẢN PHẨM
# ============================================================
def import_products(
    session: Session, validated_rows: List[dict],
) -> Tuple[int, int, List[str]]:
    """
    Thực hiện import. Chỉ import các dòng action=CREATE hoặc UPDATE.
    Trả về (created_count, updated_count, error_messages).
    """
    from app.modules.quan_ly_kho.models import Product, Category, Supplier

    created = 0
    updated = 0
    errors = []

    # Cache
    existing_cats = {c.name.lower(): c for c in session.exec(select(Category)).all()}
    existing_sups = {s.code.upper(): s for s in session.exec(select(Supplier)).all()}

    for item in validated_rows:
        if item["action"] not in ("CREATE", "UPDATE"):
            continue

        try:
            raw = item["_raw"]

            # 1. Xử lý Ngành hàng (tự tạo nếu chưa có)
            cat_obj = None
            cat_name = str(raw.get("Ngành hàng") or "").strip()
            if cat_name:
                cat_key = cat_name.lower()
                if cat_key in existing_cats:
                    cat_obj = existing_cats[cat_key]
                else:
                    # Tạo danh mục mới
                    cat_obj = Category(name=cat_name)
                    session.add(cat_obj)
                    session.flush()
                    existing_cats[cat_key] = cat_obj

            # 2. Xử lý NCC
            sup_code = str(raw.get("Nhà cung cấp") or "").strip().upper()
            sup_obj = existing_sups.get(sup_code) if sup_code else None

            # 3. Xử lý Product
            if item["action"] == "CREATE":
                product = Product(
                    sku=item["sku"],
                    name=item["name"],
                    unit=item["unit"],
                    cost_price=item["cost_price"],
                    price=item["price"],
                    stock_quantity=0,  # Không import tồn
                    tax_rate=item["tax_rate"],
                    min_stock=item["min_stock"],
                    cost_method=item["cost_method"],
                    category_id=cat_obj.id if cat_obj else None,
                    supplier_id=sup_obj.id if sup_obj else None,
                )
                session.add(product)
                created += 1

            elif item["action"] == "UPDATE":
                product = session.exec(
                    select(Product).where(Product.sku == item["sku"])
                ).first()
                if product:
                    product.name = item["name"]
                    product.unit = item["unit"]
                    product.cost_price = item["cost_price"]
                    product.price = item["price"]
                    product.tax_rate = item["tax_rate"]
                    product.min_stock = item["min_stock"]
                    product.cost_method = item["cost_method"]
                    if cat_obj:
                        product.category_id = cat_obj.id
                    if sup_obj:
                        product.supplier_id = sup_obj.id
                    session.add(product)
                    updated += 1

        except Exception as e:
            errors.append(f"Dòng {item['row_num']}: {e}")

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return 0, 0, [f"Lỗi commit: {e}"]

    return created, updated, errors
    