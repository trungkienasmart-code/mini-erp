from app.core.database import engine
from sqlmodel import Session, select
from app.modules.ban_hang.models import SaleOrder, Customer

s = Session(engine)

# Fix 1: Đơn đã trả đủ nhưng status còn CONFIRMED → chuyển thành PAID
print("=== FIX ORDERS ===")
orders = s.exec(select(SaleOrder)).all()
for o in orders:
    if o.paid_amount >= o.total_amount - 0.01 and o.status in ("CONFIRMED", "PARTIAL"):
        print(f"  {o.code}: {o.status} → PAID (đã trả đủ {o.paid_amount})")
        o.status = "PAID"
        s.add(o)
s.commit()

# Fix 2: Tính lại công nợ KH dựa trên đơn thực tế
print("\n=== FIX CUSTOMER DEBT ===")
customers = s.exec(select(Customer)).all()
for c in customers:
    # Tổng nợ = sum(total_amount - paid_amount) cho các đơn chưa hủy
    orders_of_cust = s.exec(
        select(SaleOrder)
        .where(SaleOrder.customer_id == c.id)
        .where(SaleOrder.status != "CANCELLED")
    ).all()
    correct_debt = sum(o.total_amount - o.paid_amount for o in orders_of_cust)
    correct_debt = max(0, correct_debt)
    if abs(c.current_debt - correct_debt) > 0.01:
        print(f"  {c.code} {c.name}: {c.current_debt:,.0f} → {correct_debt:,.0f}")
        c.current_debt = correct_debt
        s.add(c)
s.commit()
print("\n✅ Đã fix xong!")