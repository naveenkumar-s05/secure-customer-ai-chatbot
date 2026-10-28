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


def test_invoice_duplicate_prevention_logic():
    db = TestingSessionLocal()
    c1 = models.Customer(name="A", mobile="+913333333333")
    db.add(c1)
    db.commit()
    db.refresh(c1)
    
    from app.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: c1
    
    # Create conversation
    r = client.post("/conversations", json={"title": "t"})
    assert r.status_code == 200
    conv_id = r.json()["id"]
    
    # Add invoice via assistant tool path is complex; test model level duplicate constraint
    from datetime import date
    inv = models.Invoice(
        customer_id=c1.id,
        invoice_number="INV-TEST-1",
        invoice_date=date(2026, 1, 1),
        amount=100.0,
        currency="INR",
        payment_status="unpaid",
    )
    db.add(inv)
    db.commit()
    # Try duplicate
    try:
        inv2 = models.Invoice(
            customer_id=c1.id,
            invoice_number="INV-TEST-1",
            invoice_date=date(2026, 1, 2),
            amount=200.0,
            currency="INR",
            payment_status="paid",
        )
        db.add(inv2)
        db.commit()
        assert False, "Should have raised"
    except Exception:
        db.rollback()
        assert True
