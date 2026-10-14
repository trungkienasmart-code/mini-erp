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
    
    # ============================================================
# TEMPLATE NGÀNH HÀNG (danh mục)
# ============================================================
CATEGORY_HEADERS = ["Tên ngành hàng", "Mô tả"]


def generate_categories_template() -> bytes:
    """Tạo file Excel template cho import ngành hàng."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Ngành hàng"

    _apply_header_style(ws, CATEGORY_HEADERS, color="6f42c1")

    samples = [
        ["Nước giải khát", "Các loại nước ngọt, nước suối, bia"],
        ["Bánh kẹo", "Bánh quy, kẹo, socola"],
    ]
    for row_data in samples:
        ws.append(row_data)

    _apply_data_style(ws, len(samples), len(CATEGORY_HEADERS))
    _auto_width(ws, CATEGORY_HEADERS)

    note_ws = wb.create_sheet("Hướng dẫn")
    note_ws.column_dimensions['A'].width = 100
    notes = [
        ("HƯỚNG DẪN IMPORT NGÀNH HÀNG", True),
        ("", False),
        ("1. Cột 'Tên ngành hàng' là BẮT BUỘC.", False),
        ("2. Nếu tên đã tồn tại (không phân biệt hoa thường) → BỎ QUA.", False),
        ("3. Nếu chưa có → TẠO MỚI.", False),
        ("4. Cột 'Mô tả' không bắt buộc.", False),
        ("5. Tối đa 1,000 dòng/lần import.", False),
        ("", False),
        ("⚠️ LƯU Ý: Xóa 2 dòng ví dụ trước khi import dữ liệu thật.", False),
    ]
    for idx, (text, bold) in enumerate(notes, 1):
        cell = note_ws.cell(row=idx, column=1, value=text)
        if bold:
            cell.font = Font(bold=True, size=14, color="6f42c1")

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# ============================================================
# VALIDATE — NHÀ CUNG CẤP
# ============================================================
def validate_suppliers(session: Session, rows: List[dict]) -> Tuple[List[dict], dict]:
    """Validate từng dòng import NCC."""
    from app.modules.quan_ly_kho.models import Supplier

    results = []
    summary = {"total": len(rows), "create": 0, "update_count": 0, "error": 0}

    existing_sups = {s.code.upper(): s for s in session.exec(select(Supplier)).all()}

    for row in rows:
        row_num = row.get("_row", 0)
        errors = []

        # === Mã NCC ===
        code = row.get("Mã NCC")
        code = str(code).strip().upper() if code else ""
        if not code:
            errors.append("Thiếu Mã NCC")
        elif len(code) > 50:
            errors.append(f"Mã NCC quá dài (>{50} ký tự)")

        # === Tên NCC ===
        name = row.get("Tên NCC")
        name = str(name).strip() if name else ""
        if not name:
            errors.append("Thiếu Tên NCC")
        elif len(name) > 200:
            errors.append(f"Tên quá dài (>{200} ký tự)")

        # === SĐT ===
        phone = row.get("SĐT")
        phone = str(phone).strip() if phone else ""
        if len(phone) > 30:
            errors.append(f"SĐT quá dài (>{30} ký tự)")

        # === Email ===
        email = row.get("Email")
        email = str(email).strip() if email else ""
        if email and "@" not in email:
            errors.append("Email không hợp lệ (thiếu @)")

        # === Địa chỉ ===
        address = row.get("Địa chỉ")
        address = str(address).strip() if address else ""

        # === MST ===
        tax_code = row.get("Mã số thuế")
        tax_code = str(tax_code).strip() if tax_code else ""

        # === Số ngày nợ ===
        try:
            term_days = int(row.get("Số ngày nợ") or 30)
            if term_days < 0:
                errors.append("Số ngày nợ < 0")
        except (ValueError, TypeError):
            term_days = 30
            errors.append("Số ngày nợ không hợp lệ")

        # === Xác định CREATE/UPDATE ===
        action = ""
        if code and not errors:
            if code in existing_sups:
                action = "UPDATE"
                summary["update_count"] += 1
            else:
                action = "CREATE"
                summary["create"] += 1

        if errors:
            action = "ERROR"
            summary["error"] += 1

        results.append({
            "row_num": row_num,
            "code": code or "—",
            "name": name or "—",
            "phone": phone or "—",
            "email": email or "—",
            "address": address or "—",
            "tax_code": tax_code or "—",
            "term_days": term_days,
            "action": action,
            "errors": errors,
            "_raw": row,
        })

    return results, summary


# ============================================================
# EXECUTE IMPORT — NHÀ CUNG CẤP
# ============================================================
def import_suppliers(
    session: Session, validated_rows: List[dict],
) -> Tuple[int, int, List[str]]:
    """Import NCC."""
    from app.modules.quan_ly_kho.models import Supplier

    created = 0
    updated = 0
    errors = []

    for item in validated_rows:
        if item["action"] not in ("CREATE", "UPDATE"):
            continue

        try:
            if item["action"] == "CREATE":
                sup = Supplier(
                    code=item["code"],
                    name=item["name"],
                    phone=item["phone"].replace("—", ""),
                    email=item["email"].replace("—", ""),
                    address=item["address"].replace("—", ""),
                    tax_code=item["tax_code"].replace("—", ""),
                    payment_term_days=item["term_days"],
                )
                session.add(sup)
                created += 1

            elif item["action"] == "UPDATE":
                sup = session.exec(
                    select(Supplier).where(Supplier.code == item["code"])
                ).first()
                if sup:
                    sup.name = item["name"]
                    sup.phone = item["phone"].replace("—", "")
                    sup.email = item["email"].replace("—", "")
                    sup.address = item["address"].replace("—", "")
                    sup.tax_code = item["tax_code"].replace("—", "")
                    sup.payment_term_days = item["term_days"]
                    session.add(sup)
                    updated += 1

        except Exception as e:
            errors.append(f"Dòng {item['row_num']}: {e}")

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return 0, 0, [f"Lỗi commit: {e}"]

    return created, updated, errors


# ============================================================
# VALIDATE — NGÀNH HÀNG
# ============================================================
def validate_categories(session: Session, rows: List[dict]) -> Tuple[List[dict], dict]:
    """Validate từng dòng import ngành hàng."""
    from app.modules.quan_ly_kho.models import Category

    results = []
    summary = {"total": len(rows), "create": 0, "update_count": 0, "error": 0}

    existing_cats = {c.name.lower(): c for c in session.exec(select(Category)).all()}

    for row in rows:
        row_num = row.get("_row", 0)
        errors = []

        name = row.get("Tên ngành hàng")
        name = str(name).strip() if name else ""
        if not name:
            errors.append("Thiếu Tên ngành hàng")
        elif len(name) > 100:
            errors.append(f"Tên quá dài (>{100} ký tự)")

        note = row.get("Mô tả")
        note = str(note).strip() if note else ""

        # Xác định action
        action = ""
        if name and not errors:
            if name.lower() in existing_cats:
                action = "SKIP"  # Đã có → bỏ qua
                # Không tăng create/update
            else:
                action = "CREATE"
                summary["create"] += 1

        if errors:
            action = "ERROR"
            summary["error"] += 1

        results.append({
            "row_num": row_num,
            "name": name or "—",
            "note": note or "—",
            "action": action,
            "errors": errors,
            "_raw": row,
        })

    return results, summary


# ============================================================
# EXECUTE IMPORT — NGÀNH HÀNG
# ============================================================
def import_categories(
    session: Session, validated_rows: List[dict],
) -> Tuple[int, List[str]]:
    """Import ngành hàng (danh mục)."""
    from app.modules.quan_ly_kho.models import Category

    created = 0
    errors = []

    for item in validated_rows:
        if item["action"] != "CREATE":
            continue

        try:
            cat = Category(
                name=item["name"],
                note=item["note"].replace("—", ""),
            )
            session.add(cat)
            created += 1
        except Exception as e:
            errors.append(f"Dòng {item['row_num']}: {e}")

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return 0, [f"Lỗi commit: {e}"]

    return created, errors
    
    # ============================================================
# TEMPLATE ĐƠN MUA HÀNG (2 SHEET)
# ============================================================
PURCHASE_HEADER_COLS = ["Mã đơn", "Ngày", "Mã NCC", "Số HĐ NCC", "Ngày HĐ NCC", "Ghi chú"]
PURCHASE_LINE_COLS = ["Mã đơn", "Mã SKU", "SL", "Đơn giá", "VAT (%)", "Ghi chú"]


def generate_purchase_template() -> bytes:
    """Template đơn mua hàng có 2 sheet: Header + Chi tiết."""
    wb = Workbook()

    # === Sheet 1: Header ===
    ws1 = wb.active
    ws1.title = "Đơn mua"
    _apply_header_style(ws1, PURCHASE_HEADER_COLS, color="fd7e14")

    sample_headers = [
        ["PN001", "14/10/2026", "NCC001", "INV-2026-001", "14/10/2026", "Nhập hàng tháng 10"],
        ["PN002", "15/10/2026", "NCC002", "INV-2026-002", "15/10/2026", ""],
    ]
    for r in sample_headers:
        ws1.append(r)
    _apply_data_style(ws1, len(sample_headers), len(PURCHASE_HEADER_COLS))
    _auto_width(ws1, PURCHASE_HEADER_COLS)

    # === Sheet 2: Chi tiết ===
    ws2 = wb.create_sheet("Chi tiết")
    _apply_header_style(ws2, PURCHASE_LINE_COLS, color="20c997")

    sample_lines = [
        ["PN001", "SP001", 100, 5000, 10, ""],
        ["PN001", "SP002", 50, 6000, 10, ""],
        ["PN002", "SP001", 200, 4800, 10, "Đợt 2"],
    ]
    for r in sample_lines:
        ws2.append(r)
    _apply_data_style(ws2, len(sample_lines), len(PURCHASE_LINE_COLS))
    _auto_width(ws2, PURCHASE_LINE_COLS)

    # === Sheet 3: Hướng dẫn ===
    ws3 = wb.create_sheet("Hướng dẫn")
    ws3.column_dimensions['A'].width = 100
    notes = [
        ("HƯỚNG DẪN IMPORT ĐƠN MUA HÀNG", True),
        ("", False),
        ("📋 CẤU TRÚC FILE (2 sheet):", True),
        ("  • Sheet 'Đơn mua': chứa thông tin header của từng đơn.", False),
        ("  • Sheet 'Chi tiết': chứa các dòng sản phẩm của các đơn.", False),
        ("", False),
        ("📝 QUY TẮC:", True),
        ("1. Cột 'Mã đơn' ở cả 2 sheet phải khớp nhau để liên kết.", False),
        ("2. Cột 'Mã NCC' phải tồn tại trong hệ thống (import NCC trước).", False),
        ("3. Cột 'Mã SKU' phải tồn tại trong hệ thống (import SP trước).", False),
        ("4. Đơn hàng sẽ được tạo ở trạng thái NHÁP (DRAFT).", False),
        ("5. Sau khi import, vào Mua hàng → Duyệt → Nhận hàng → Nhập kho.", False),
        ("6. Hệ thống TỰ TÍNH: thành tiền, VAT, tổng cộng.", False),
        ("7. Không tự động nhập kho.", False),
        ("", False),
        ("⚠️ LƯU Ý: Xóa 2 dòng ví dụ ở mỗi sheet trước khi import.", False),
    ]
    for idx, (text, bold) in enumerate(notes, 1):
        cell = ws3.cell(row=idx, column=1, value=text)
        if bold:
            cell.font = Font(bold=True, size=13, color="fd7e14")

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def parse_purchase_excel(file_content: bytes) -> Tuple[List[dict], str]:
    """
    Parse file Excel đơn mua 2 sheet.
    Trả về list các đơn hàng có lines.
    """
    try:
        wb = load_workbook(io.BytesIO(file_content), data_only=True)

        # Tìm sheet Header
        if "Đơn mua" not in wb.sheetnames:
            return [], "Thiếu sheet 'Đơn mua'"
        if "Chi tiết" not in wb.sheetnames:
            return [], "Thiếu sheet 'Chi tiết'"

        ws_h = wb["Đơn mua"]
        ws_l = wb["Chi tiết"]

        # === Đọc header sheet ===
        header_map_h = {}
        for idx, cell in enumerate(ws_h[1]):
            if cell.value:
                header_map_h[str(cell.value).strip()] = idx

        orders = {}
        for row in ws_h.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            code = row[header_map_h.get("Mã đơn", 0)]
            code = str(code).strip().upper() if code else ""
            if not code:
                continue

            orders[code] = {
                "code": code,
                "date": row[header_map_h.get("Ngày", 1)] if header_map_h.get("Ngày", 1) < len(row) else None,
                "supplier_code": str(row[header_map_h.get("Mã NCC", 2)] or "").strip().upper()
                    if header_map_h.get("Mã NCC", 2) < len(row) else "",
                "invoice_no": str(row[header_map_h.get("Số HĐ NCC", 3)] or "").strip()
                    if header_map_h.get("Số HĐ NCC", 3) < len(row) else "",
                "invoice_date": row[header_map_h.get("Ngày HĐ NCC", 4)] if header_map_h.get("Ngày HĐ NCC", 4) < len(row) else None,
                "note": str(row[header_map_h.get("Ghi chú", 5)] or "").strip()
                    if header_map_h.get("Ghi chú", 5) < len(row) else "",
                "lines": [],
            }

        # === Đọc chi tiết sheet ===
        header_map_l = {}
        for idx, cell in enumerate(ws_l[1]):
            if cell.value:
                header_map_l[str(cell.value).strip()] = idx

        for row in ws_l.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            code = row[header_map_l.get("Mã đơn", 0)]
            code = str(code).strip().upper() if code else ""
            if not code:
                continue

            if code not in orders:
                # Dòng chi tiết không có header tương ứng → skip
                continue

            orders[code]["lines"].append({
                "sku": str(row[header_map_l.get("Mã SKU", 1)] or "").strip().upper()
                    if header_map_l.get("Mã SKU", 1) < len(row) else "",
                "quantity": row[header_map_l.get("SL", 2)] if header_map_l.get("SL", 2) < len(row) else 0,
                "unit_price": row[header_map_l.get("Đơn giá", 3)] if header_map_l.get("Đơn giá", 3) < len(row) else 0,
                "tax_rate": row[header_map_l.get("VAT (%)", 4)] if header_map_l.get("VAT (%)", 4) < len(row) else 0,
                "note": str(row[header_map_l.get("Ghi chú", 5)] or "").strip()
                    if header_map_l.get("Ghi chú", 5) < len(row) else "",
            })

        result = list(orders.values())

        if len(result) > MAX_ROWS:
            return [], f"File có {len(result)} đơn, vượt quá giới hạn {MAX_ROWS}"

        return result, "OK"

    except Exception as e:
        return [], f"Lỗi đọc file: {e}"


def validate_purchase(session: Session, orders: List[dict]) -> Tuple[List[dict], dict]:
    """Validate các đơn mua."""
    from app.modules.quan_ly_kho.models import Supplier, Product
    from app.modules.mua_hang.models import PurchaseOrder

    results = []
    summary = {"total": len(orders), "create": 0, "update_count": 0, "error": 0}

    existing_sups = {s.code.upper(): s for s in session.exec(select(Supplier)).all()}
    existing_products = {p.sku.upper(): p for p in session.exec(select(Product)).all()}
    existing_orders = {o.code.upper(): o for o in session.exec(select(PurchaseOrder)).all()}

    for order in orders:
        errors = []
        code = order["code"]

        # Check mã đơn trùng
        if code in existing_orders:
            errors.append(f"Mã đơn '{code}' đã tồn tại")

        # Check NCC
        sup_code = order["supplier_code"]
        sup_obj = existing_sups.get(sup_code)
        if not sup_code:
            errors.append("Thiếu Mã NCC")
        elif not sup_obj:
            errors.append(f"NCC '{sup_code}' không tồn tại")

        # Check lines
        valid_lines = []
        line_errors = []
        if not order["lines"]:
            errors.append("Đơn không có sản phẩm nào")
        else:
            for idx, line in enumerate(order["lines"], 1):
                lerr = []
                sku = line["sku"]

                if not sku:
                    lerr.append("Thiếu Mã SKU")
                elif sku not in existing_products:
                    lerr.append(f"SP '{sku}' không tồn tại")

                try:
                    qty = int(line["quantity"] or 0)
                    if qty <= 0:
                        lerr.append("SL phải > 0")
                except (ValueError, TypeError):
                    qty = 0
                    lerr.append("SL không hợp lệ")

                try:
                    price = float(line["unit_price"] or 0)
                    if price < 0:
                        lerr.append("Đơn giá < 0")
                except (ValueError, TypeError):
                    price = 0
                    lerr.append("Đơn giá không hợp lệ")

                try:
                    tax = float(line["tax_rate"] or 0)
                    if tax < 0 or tax > 100:
                        lerr.append("VAT phải 0-100")
                except (ValueError, TypeError):
                    tax = 0
                    lerr.append("VAT không hợp lệ")

                if lerr:
                    line_errors.append(f"Dòng {idx}: {'; '.join(lerr)}")
                else:
                    valid_lines.append({
                        "sku": sku,
                        "product_id": existing_products[sku].id,
                        "quantity": qty,
                        "unit_price": price,
                        "tax_rate": tax,
                        "note": line["note"],
                    })

        errors.extend(line_errors)

        if errors:
            action = "ERROR"
            summary["error"] += 1
        else:
            action = "CREATE"
            summary["create"] += 1

        # Tính tổng tiền
        subtotal = 0.0
        tax_total = 0.0
        for l in valid_lines:
            amt = l["quantity"] * l["unit_price"]
            subtotal += amt
            tax_total += amt * l["tax_rate"] / 100

        results.append({
            "row_num": order.get("row_num", 0),
            "code": code,
            "supplier_code": sup_code or "—",
            "supplier_name": sup_obj.name if sup_obj else "—",
            "invoice_no": order["invoice_no"] or "—",
            "line_count": len(order["lines"]),
            "valid_line_count": len(valid_lines),
            "subtotal": subtotal,
            "tax_total": tax_total,
            "total": subtotal + tax_total,
            "action": action,
            "errors": errors,
            "_raw": order,
            "_valid_lines": valid_lines,
            "_supplier_id": sup_obj.id if sup_obj else None,
        })

    return results, summary


def import_purchase(
    session: Session, validated_orders: List[dict],
    user_id: Optional[int] = None,
) -> Tuple[int, int, List[str]]:
    """Import đơn mua hàng (status=DRAFT)."""
    from app.modules.mua_hang.models import PurchaseOrder, PurchaseOrderLine

    created = 0
    line_count = 0
    errors = []

    for item in validated_orders:
        if item["action"] != "CREATE":
            continue

        try:
            order = PurchaseOrder(
                code=item["code"],
                supplier_id=item["_supplier_id"],
                user_id=user_id,
                status="DRAFT",
                payment_method="DEBT",
                supplier_invoice_no=item["_raw"].get("invoice_no", ""),
                subtotal=item["subtotal"],
                tax_amount=item["tax_total"],
                total_amount=item["total"],
                note=item["_raw"].get("note", ""),
            )
            session.add(order)
            session.flush()

            for l in item["_valid_lines"]:
                line = PurchaseOrderLine(
                    order_id=order.id,
                    product_id=l["product_id"],
                    quantity=l["quantity"],
                    base_quantity=l["quantity"],
                    unit_price=l["unit_price"],
                    tax_rate=l["tax_rate"],
                    line_subtotal=l["quantity"] * l["unit_price"],
                    line_tax=l["quantity"] * l["unit_price"] * l["tax_rate"] / 100,
                    line_total=l["quantity"] * l["unit_price"] * (1 + l["tax_rate"] / 100),
                )
                session.add(line)
                line_count += 1

            created += 1

        except Exception as e:
            errors.append(f"Đơn {item['code']}: {e}")

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return 0, 0, [f"Lỗi commit: {e}"]

    return created, line_count, errors