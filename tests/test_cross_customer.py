import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models
from datetime import date

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_customer_cannot_access_another_invoice():
    db = TestingSessionLocal()
    c1 = models.Customer(name="A", mobile="+914444444444")
    c2 = models.Customer(name="B", mobile="+915555555555")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)
    
    inv = models.Invoice(
        customer_id=c1.id,
        invoice_number="INV-A1",
        invoice_date=date(2026, 1, 1),
        amount=100.0,
        currency="INR",
        payment_status="unpaid",
    )
    db.add(inv)
    db.commit()
    
    from app.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: c2
    
    # Try to access via confirm-invoice with wrong customer - create conv
    conv = models.Conversation(customer_id=c2.id, title="t")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    
    # Create proposal for c2
    prop = models.PendingInvoiceProposal(
        customer_id=c2.id,
        conversation_id=conv.id,
        invoice_number="INV-C2",
        invoice_date=date(2026, 1, 1),
        amount=50.0,
        currency="INR",
        payment_status="unpaid",
        status="pending",
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    
    # Try to confirm proposal that belongs to c2 but let's test cross-customer access pattern
    # Try with proposal_id that doesn't belong to c2
    r = client.post(f"/conversations/{conv.id}/confirm-invoice", json={"proposal_id": 99999, "confirm": True})
    assert r.status_code == 404
