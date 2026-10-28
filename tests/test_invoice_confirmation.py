import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import date

from app.database import Base, get_db
from app.main import app
from app import models

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommaker=False, autoflush=False, bind=engine)
# Fix typo in name
from sqlalchemy.orm import sessionmaker as sm
TestingSessionLocal = sm(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_duplicate_confirmation_prevention():
    db = TestingSessionLocal()
    c1 = models.Customer(name="A", mobile="+916666666666")
    db.add(c1)
    db.commit()
    db.refresh(c1)
    
    from app.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: c1
    
    conv = models.Conversation(customer_id=c1.id, title="t")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    
    prop = models.PendingInvoiceProposal(
        customer_id=c1.id,
        conversation_id=conv.id,
        invoice_number="INV-DUP1",
        invoice_date=date(2026, 2, 1),
        amount=100.0,
        currency="INR",
        payment_status="unpaid",
        status="pending",
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    
    # First confirm
    r1 = client.post(f"/conversations/{conv.id}/confirm-invoice", json={"proposal_id": prop.id, "confirm": True})
    assert r1.status_code == 200
    
    # Second confirm should be rejected
    r2 = client.post(f"/conversations/{conv.id}/confirm-invoice", json={"proposal_id": prop.id, "confirm": True})
    assert r2.status_code == 409
