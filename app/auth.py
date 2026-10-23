
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi.security import HTTPBearer

from jose import jwt, JWTError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, DEV_OTP_ENABLED
from app.database import get_db
from app.models import Customer, OTPChallenge
from app.schemas import OTPRequest, OTPVerify, TokenResponse, CustomerResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
ALGORITHM = "HS256"


def normalize_mobile(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        raise HTTPException(400, "Enter a valid Indian mobile number")
    return "+91" + digits


def hash_otp(otp: str) -> str:
    return hmac.new(
        SECRET_KEY.encode(), otp.encode(), hashlib.sha256
    ).hexdigest()


@router.post("/request-otp")
def request_otp(body: OTPRequest, db: Session = Depends(get_db)):
    if not DEV_OTP_ENABLED:
        raise HTTPException(503, "OTP delivery adapter is not configured")

    mobile = normalize_mobile(body.mobile)
    customer = db.query(Customer).filter_by(mobile=mobile).first()

    # Generic response avoids revealing whether a customer exists.
    if not customer:
        return {"message": "If the account exists, an OTP has been sent."}

    now = datetime.now(timezone.utc)
    latest = (
        db.query(OTPChallenge)
        .filter_by(mobile=mobile)
        .order_by(OTPChallenge.id.desc())
        .first()
    )

    if latest and (now - latest.created_at).total_seconds() < 60:
        raise HTTPException(429, "Please wait before requesting another OTP")

    otp = f"{secrets.randbelow(1_000_000):06d}"

    challenge = OTPChallenge(
        mobile=mobile,
        otp_hash=hash_otp(otp),
        expires_at=now + timedelta(minutes=5),
        attempts=0,
        used=False,
    )
    db.add(challenge)
    db.commit()

    # Development delivery: terminal only, never included in API response.
    print(f"[DEV OTP delivery] mobile={mobile} code={otp}")

    return {"message": "If the account exists, an OTP has been sent."}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(body: OTPVerify, db: Session = Depends(get_db)):
    mobile = normalize_mobile(body.mobile)
    now = datetime.now(timezone.utc)

    challenge = (
        db.query(OTPChallenge)
        .filter_by(mobile=mobile, used=False)
        .order_by(OTPChallenge.id.desc())
        .first()
    )

    if not challenge or challenge.expires_at <= now:
        raise HTTPException(401, "OTP invalid or expired")

    if challenge.attempts >= 5:
        raise HTTPException(429, "OTP verification attempt limit reached")

    challenge.attempts += 1

    if not hmac.compare_digest(challenge.otp_hash, hash_otp(body.otp)):
        if challenge.attempts >= 5:
            challenge.used = True
        db.commit()
        raise HTTPException(401, "OTP invalid or expired")

    challenge.used = True
    customer = db.query(Customer).filter_by(mobile=mobile).first()

    if not customer:
        db.commit()
        raise HTTPException(401, "OTP invalid or expired")

    token = jwt.encode(
        {
            "sub": str(customer.id),
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    db.commit()
    return {"access_token": token, "token_type": "bearer"}


def get_current_customer(
    authorization: str = Depends(HTTPBearer()),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            authorization.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        customer_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired access token")

    customer = db.query(Customer).filter_by(id=customer_id).first()
    if not customer:
        raise HTTPException(401, "Invalid or expired access token")
    return customer


@router.get("/me", response_model=CustomerResponse)
def me(customer: Customer = Depends(get_current_customer)):
    return customer
