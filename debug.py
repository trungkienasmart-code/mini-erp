from app.core.database import engine
from sqlmodel import Session, select
from app.modules.ban_hang.models import SalePayment, SaleOrder

s = Session(engine)

print("=== PAYMENTS ===")
for p in s.exec(select(SalePayment)).all():
    print(f"ID={p.id}, order_id={p.order_id}, amount={p.amount}, "
          f"method={p.payment_method}, at={p.created_at.strftime('%d/%m %H:%M')}")

print("\n=== ORDERS ===")
for o in s.exec(select(SaleOrder)).all():
    print(f"{o.code}: status={o.status}, paid={o.paid_amount}/{o.total_amount}, "
          f"method={o.payment_method}")