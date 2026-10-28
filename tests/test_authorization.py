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


def test_cross_customer_isolation_conversations():
    db = TestingSessionLocal()
    # Create two customers
    c1 = models.Customer(name="A", mobile="+911111111111")
    c2 = models.Customer(name="B", mobile="+912222222222")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)
    
    from app.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: c1
    r = client.post("/conversations", json={"title": "c1"})
    assert r.status_code == 200
    conv_id = r.json()["id"]
    
    # Switch to c2
    app.dependency_overrides[get_current_customer] = lambda: c2
    r2 = client.get(f"/conversations/{conv_id}/messages")
    assert r2.status_code == 404
