import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

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


def test_request_otp_nonexistent_customer():
    # Should return generic message
    response = client.post("/auth/request-otp", json={"mobile": "9999999999"})
    assert response.status_code == 200
    assert "OTP" in response.json().get("message", "")


def test_verify_otp_invalid():
    response = client.post("/auth/verify-otp", json={"mobile": "9999999999", "otp": "123456"})
    assert response.status_code == 401


def test_protected_without_token():
    response = client.get("/auth/me")
    assert response.status_code in (401, 403)
