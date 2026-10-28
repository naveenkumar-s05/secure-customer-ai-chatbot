
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
MAX_OTP_ATTEMPTS = 5
OTP_REQUEST_COOLDOWN_SECONDS = 60
OTP_EXPIRY_MINUTES = 5


def normalize_mobile(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        raise HTTPException(400, "Enter a valid Indian mobile number")
    return "+91" + digits


def hash_otp(otp: str) -> str:
    # Use HMAC-SHA256 for OTP hashing
    if not SECRET_KEY:
        raise HTTPException(500, "Server configuration error")
    return hmac.new(
        SECRET_KEY.encode(), str(otp).encode(), hashlib.sha256
    ).hexdigest()


@router.post("/request-otp")
def request_otp(body: OTPRequest, db: Session = Depends(get_db)):
    if not DEV_OTP_ENABLED:
        raise HTTPException(503, "OTP delivery adapter is not configured")

    try:
        mobile = normalize_mobile(body.mobile)
    except HTTPException:
        # Avoid leaking validation details in a specific way; follow generic behavior
        raise

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

    if latest and latest.created_at is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if (now - created_at).total_seconds() < OTP_REQUEST_COOLDOWN_SECONDS:
            raise HTTPException(429, "Please wait before requesting another OTP")

    # Generate cryptographically secure OTP
    otp = f"{secrets.randbelow(1_000_000):06d}"

    try:
        challenge = OTPChallenge(
            mobile=mobile,
            otp_hash=hash_otp(otp),
            expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
            attempts=0,
            used=False,
        )
        db.add(challenge)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Failed to generate OTP")

    # Development delivery: terminal only, never included in API response.
    print("[DEV OTP delivery] requested for a registered mobile")

    return {"message": "If the account exists, an OTP has been sent."}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(body: OTPVerify, db: Session = Depends(get_db)):
    try:
        mobile = normalize_mobile(body.mobile)
    except HTTPException:
        raise

    now = datetime.now(timezone.utc)

    challenge = (
        db.query(OTPChallenge)
        .filter_by(mobile=mobile, used=False)
        .order_by(OTPChallenge.id.desc())
        .first()
    )

    if not challenge:
        raise HTTPException(401, "OTP invalid or expired")

    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        try:
            challenge.used = True
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(401, "OTP invalid or expired")

    if challenge.attempts >= MAX_OTP_ATTEMPTS:
        try:
            challenge.used = True
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(429, "OTP verification attempt limit reached")

    challenge.attempts += 1

    try:
        otp_matches = hmac.compare_digest(challenge.otp_hash, hash_otp(body.otp))
    except Exception:
        otp_matches = False

    if not otp_matches:
        try:
            if challenge.attempts >= MAX_OTP_ATTEMPTS:
                challenge.used = True
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(401, "OTP invalid or expired")

    challenge.used = True
    customer = db.query(Customer).filter_by(mobile=mobile).first()

    if not customer:
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(401, "OTP invalid or expired")

    try:
        token = jwt.encode(
            {
                "sub": str(customer.id),
                "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Failed to issue token")

    return {"access_token": token, "token_type": "bearer"}


def get_current_customer(
    authorization: str = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
):
    if not authorization or not getattr(authorization, "credentials", None):
        raise HTTPException(401, "Invalid or expired access token")
    try:
        payload = jwt.decode(
            authorization.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        if not payload or "sub" not in payload:
            raise HTTPException(401, "Invalid or expired access token")
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
