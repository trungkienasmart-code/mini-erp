# app/modules/nhap_lieu/router.py
import os
import uuid
import json
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.core.config import BASE_DIR
from app.modules.auth.dependencies import require_login
from app.modules.nhap_lieu import services


router = APIRouter(prefix="/import", tags=["Import"])


# ============================================================
# CONSTANTS
# ============================================================
TEMP_DIR = BASE_DIR / "temp_uploads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

IMPORT_TYPES = {
    "products": {
        "name": "Sản phẩm",
        "icon": "bi-box-seam",
        "color": "primary",
        "description": "Import danh sách sản phẩm + tự tạo ngành hàng",
        "headers": services.PRODUCT_HEADERS,
        "supported": True,
    },
    "suppliers": {
        "name": "Nhà cung cấp",
        "icon": "bi-truck",
        "color": "danger",
        "description": "Import danh sách nhà cung cấp",
        "headers": services.SUPPLIER_HEADERS,
        "supported": True,
    },
    "categories": {
        "name": "Ngành hàng",
        "icon": "bi-tags",
        "color": "purple",
        "description": "Import danh sách ngành hàng (danh mục)",
        "headers": services.CATEGORY_HEADERS,
        "supported": True,
    },
    "purchase": {
        "name": "Đơn mua hàng",
        "icon": "bi-cart-plus",
        "color": "warning",
        "description": "Import đơn mua hàng (ở trạng thái Nháp)",
        "headers": ["(file có 2 sheet: Đơn mua + Chi tiết)"],
        "supported": True,   # ← Đổi từ False → True
    },
}


# ============================================================
# HELPERS
# ============================================================
def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


def _cleanup_old_temp_files(max_age_hours: int = 24):
    """Xóa file temp cũ hơn X giờ."""
    try:
        now = datetime.now().timestamp()
        for f in TEMP_DIR.glob("*.xlsx"):
            if (now - f.stat().st_mtime) > max_age_hours * 3600:
                f.unlink()
    except Exception:
        pass


# ============================================================
# TRANG CHÍNH
# ============================================================
@router.get("/")
def import_home(
    request: Request,
    user=Depends(require_login),
):
    return templates.TemplateResponse(
        request=request,
        name="nhap_lieu/index.html",
        context={
            "user": user,
            "import_types": IMPORT_TYPES,
        },
    )


# ============================================================
# TẢI TEMPLATE
# ============================================================
@router.get("/template/{import_type}")
def download_template(
    import_type: str,
    user=Depends(require_login),
):
    if import_type == "products":
        data = services.generate_products_template()
        filename = "template_san_pham.xlsx"
    elif import_type == "suppliers":
        data = services.generate_suppliers_template()
        filename = "template_nha_cung_cap.xlsx"
    elif import_type == "categories":
        data = services.generate_categories_template()
        filename = "template_nganh_hang.xlsx"
    elif import_type == "purchase":
        data = services.generate_purchase_template()
        filename = "template_don_mua.xlsx"
    else:
        return _redirect_with_msg("/import/", "error", f"Loại '{import_type}' chưa hỗ trợ")

    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# UPLOAD + PREVIEW
# ============================================================
@router.get("/upload/{import_type}")
def upload_form(
    import_type: str,
    request: Request,
    user=Depends(require_login),
):
    """Form upload file."""
    if import_type not in IMPORT_TYPES:
        return _redirect_with_msg("/import/", "error", "Loại import không hợp lệ")

    type_info = IMPORT_TYPES[import_type]

    return templates.TemplateResponse(
        request=request,
        name="nhap_lieu/upload.html",
        context={
            "user": user,
            "import_type": import_type,
            "type_info": type_info,
        },
    )


@router.post("/upload/{import_type}")
async def upload_process(
    import_type: str,
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Nhận file, parse, validate, hiện preview."""
    if import_type not in IMPORT_TYPES:
        return _redirect_with_msg("/import/", "error", "Loại import không hợp lệ")

    type_info = IMPORT_TYPES[import_type]
    if not type_info.get("supported"):
        return _redirect_with_msg(
            "/import/", "error",
            f"Loại '{type_info['name']}' chưa được hỗ trợ"
        )

    # Validate file
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return _redirect_with_msg(
            f"/import/upload/{import_type}",
            "error",
            "Chỉ chấp nhận file Excel (.xlsx)"
        )

    content = await file.read()
    if len(content) > services.MAX_FILE_SIZE:
        return _redirect_with_msg(
            f"/import/upload/{import_type}",
            "error",
            f"File vượt quá {services.MAX_FILE_SIZE // 1024 // 1024}MB"
        )

    _cleanup_old_temp_files()

    # Lưu file temp
    temp_id = uuid.uuid4().hex
    temp_file = TEMP_DIR / f"{temp_id}.xlsx"
    with open(temp_file, "wb") as f:
        f.write(content)

        # Parse + Validate theo loại
    if import_type == "products":
        rows, msg = services.parse_excel(content, services.PRODUCT_HEADERS)
        if msg != "OK":
            temp_file.unlink()
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        if not rows:
            temp_file.unlink()
            return _redirect_with_msg(
                f"/import/upload/{import_type}", "error", "File không có dữ liệu"
            )
        validated, summary = services.validate_products(session, rows)

    elif import_type == "suppliers":
        rows, msg = services.parse_excel(content, services.SUPPLIER_HEADERS)
        if msg != "OK":
            temp_file.unlink()
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        if not rows:
            temp_file.unlink()
            return _redirect_with_msg(
                f"/import/upload/{import_type}", "error", "File không có dữ liệu"
            )
        validated, summary = services.validate_suppliers(session, rows)

    elif import_type == "categories":
        rows, msg = services.parse_excel(content, services.CATEGORY_HEADERS)
        if msg != "OK":
            temp_file.unlink()
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        if not rows:
            temp_file.unlink()
            return _redirect_with_msg(
                f"/import/upload/{import_type}", "error", "File không có dữ liệu"
            )
        validated, summary = services.validate_categories(session, rows)

    elif import_type == "purchase":
        orders, msg = services.parse_purchase_excel(content)
        if msg != "OK":
            temp_file.unlink()
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        if not orders:
            temp_file.unlink()
            return _redirect_with_msg(
                f"/import/upload/{import_type}", "error", "File không có đơn nào"
            )
        validated, summary = services.validate_purchase(session, orders)

    else:
        temp_file.unlink()
        return _redirect_with_msg(
            f"/import/upload/{import_type}", "error", "Chưa hỗ trợ"
        )

    return templates.TemplateResponse(
        request=request,
        name="nhap_lieu/preview.html",
        context={
            "user": user,
            "import_type": import_type,
            "type_info": type_info,
            "temp_id": temp_id,
            "filename": filename,
            "rows": validated,
            "summary": summary,
        },
    )


# ============================================================
# CONFIRM IMPORT
# ============================================================
@router.post("/confirm/{import_type}")
async def confirm_import(
    import_type: str,
    request: Request,
    temp_id: str = Form(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Thực hiện import từ file temp."""
    if import_type not in IMPORT_TYPES:
        return _redirect_with_msg("/import/", "error", "Loại import không hợp lệ")

    temp_file = TEMP_DIR / f"{temp_id}.xlsx"
    if not temp_file.exists():
        return _redirect_with_msg(
            "/import/", "error",
            "File tạm không tồn tại hoặc đã hết hạn. Vui lòng upload lại."
        )

    content = temp_file.read_bytes()

    from app.modules.auth.services import write_audit

    # === SẢN PHẨM ===
    if import_type == "products":
        rows, msg = services.parse_excel(content, services.PRODUCT_HEADERS)
        if msg != "OK":
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        validated, _ = services.validate_products(session, rows)
        created, updated, errors = services.import_products(session, validated)

        write_audit(
            session, user.id, "IMPORT", "product", None,
            description=f"Import SP: {created} mới, {updated} cập nhật",
            ip=request.client.host if request.client else "",
        )
        session.commit()

        msg_out = f"✅ Import thành công: {created} sản phẩm mới, {updated} cập nhật"

    # === NHÀ CUNG CẤP ===
    elif import_type == "suppliers":
        rows, msg = services.parse_excel(content, services.SUPPLIER_HEADERS)
        if msg != "OK":
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        validated, _ = services.validate_suppliers(session, rows)
        created, updated, errors = services.import_suppliers(session, validated)

        write_audit(
            session, user.id, "IMPORT", "supplier", None,
            description=f"Import NCC: {created} mới, {updated} cập nhật",
            ip=request.client.host if request.client else "",
        )
        session.commit()

        msg_out = f"✅ Import thành công: {created} NCC mới, {updated} cập nhật"

    # === NGÀNH HÀNG ===
    elif import_type == "categories":
        rows, msg = services.parse_excel(content, services.CATEGORY_HEADERS)
        if msg != "OK":
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        validated, summary = services.validate_categories(session, rows)
        created, errors = services.import_categories(session, validated)

        skipped = summary.get("create", 0) - created if summary else 0
        write_audit(
            session, user.id, "IMPORT", "category", None,
            description=f"Import ngành hàng: {created} mới",
            ip=request.client.host if request.client else "",
        )
        session.commit()

        msg_out = f"✅ Import thành công: {created} ngành hàng mới"
    # === ĐƠN MUA HÀNG ===
    elif import_type == "purchase":
        orders, msg = services.parse_purchase_excel(content)
        if msg != "OK":
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)
        validated, _ = services.validate_purchase(session, orders)
        created, line_count, errors = services.import_purchase(
            session, validated, user_id=user.id,
        )

        write_audit(
            session, user.id, "IMPORT", "purchase_order", None,
            description=f"Import đơn mua: {created} đơn, {line_count} dòng SP",
            ip=request.client.host if request.client else "",
        )
        session.commit()

        msg_out = f"✅ Import thành công: {created} đơn mua ({line_count} dòng SP). Trạng thái: Nháp"

    else:
        return _redirect_with_msg("/import/", "error", "Loại import không được hỗ trợ")

    # Xóa file temp
    try:
        temp_file.unlink()
    except Exception:
        pass

    if errors:
        msg_out += f". Có {len(errors)} lỗi nhỏ."

    return _redirect_with_msg("/import/", "success", msg_out)


# ============================================================
# CANCEL
# ============================================================
@router.post("/cancel")
def cancel_import(
    temp_id: str = Form(...),
    user=Depends(require_login),
):
    """Hủy bỏ import, xóa file temp."""
    temp_file = TEMP_DIR / f"{temp_id}.xlsx"
    if temp_file.exists():
        try:
            temp_file.unlink()
        except Exception:
            pass
    return _redirect_with_msg("/import/", "success", "Đã hủy import")