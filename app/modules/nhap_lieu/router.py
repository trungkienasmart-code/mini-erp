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
    },
    "suppliers": {
        "name": "Nhà cung cấp",
        "icon": "bi-truck",
        "color": "danger",
        "description": "Import danh sách nhà cung cấp",
        "headers": services.SUPPLIER_HEADERS,
    },
    "purchase": {
        "name": "Đơn mua hàng",
        "icon": "bi-cart-plus",
        "color": "warning",
        "description": "Import đơn mua hàng (ở trạng thái Nháp)",
        "headers": [],
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
    """Tải file template Excel theo loại."""
    if import_type == "products":
        data = services.generate_products_template()
        filename = "template_san_pham.xlsx"
    elif import_type == "suppliers":
        data = services.generate_suppliers_template()
        filename = f"template_nha_cung_cap.xlsx"
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

    # Validate
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

    # Cleanup file cũ
    _cleanup_old_temp_files()

    # Lưu file temp
    temp_id = uuid.uuid4().hex
    temp_file = TEMP_DIR / f"{temp_id}.xlsx"
    with open(temp_file, "wb") as f:
        f.write(content)

    # Parse
    if import_type == "products":
        rows, msg = services.parse_excel(content, services.PRODUCT_HEADERS)
    elif import_type == "suppliers":
        rows, msg = services.parse_excel(content, services.SUPPLIER_HEADERS)
    else:
        return _redirect_with_msg(
            f"/import/upload/{import_type}",
            "error",
            "Chưa hỗ trợ loại import này"
        )

    if msg != "OK":
        temp_file.unlink()
        return _redirect_with_msg(
            f"/import/upload/{import_type}",
            "error",
            msg
        )

    if not rows:
        temp_file.unlink()
        return _redirect_with_msg(
            f"/import/upload/{import_type}",
            "error",
            "File không có dữ liệu"
        )

    # Validate + preview
    if import_type == "products":
        validated, summary = services.validate_products(session, rows)
    elif import_type == "suppliers":
        # Placeholder cho Buổi 3B
        validated, summary = [], {"total": 0, "create": 0, "update": 0, "error": 0}

    # Lưu kết quả validate vào session JSON (để confirm dùng lại)
    # ⚠️ Không lưu cả file — chỉ lưu tên temp + validated data

    type_info = IMPORT_TYPES[import_type]

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

    # Kiểm tra file temp tồn tại
    temp_file = TEMP_DIR / f"{temp_id}.xlsx"
    if not temp_file.exists():
        return _redirect_with_msg(
            "/import/",
            "error",
            "File tạm không tồn tại hoặc đã hết hạn. Vui lòng upload lại."
        )

    # Đọc lại file
    content = temp_file.read_bytes()

    # Parse + Validate lại (đảm bảo an toàn)
    if import_type == "products":
        rows, msg = services.parse_excel(content, services.PRODUCT_HEADERS)
        if msg != "OK":
            return _redirect_with_msg(f"/import/upload/{import_type}", "error", msg)

        validated, _ = services.validate_products(session, rows)
        created, updated, errors = services.import_products(session, validated)

        # Audit log
        from app.modules.auth.services import write_audit
        write_audit(
            session, user.id, "IMPORT", "product", None,
            description=f"Import {created} sản phẩm mới, {updated} cập nhật",
            ip=request.client.host if request.client else "",
        )
        session.commit()

        # Xóa file temp
        try:
            temp_file.unlink()
        except Exception:
            pass

        msg = f"✅ Import thành công: {created} sản phẩm mới, {updated} cập nhật"
        if errors:
            msg += f". Có {len(errors)} lỗi nhỏ."

        return _redirect_with_msg("/import/", "success", msg)

    else:
        return _redirect_with_msg(
            "/import/",
            "error",
            "Loại import này chưa được hỗ trợ"
        )


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