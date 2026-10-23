
from datetime import date

from pydantic import BaseModel, Field


class OTPRequest(BaseModel):
    mobile: str


class OTPVerify(BaseModel):
    mobile: str
    otp: str = Field(min_length=6, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CustomerResponse(BaseModel):
    id: int
    name: str
    mobile: str

    class Config:
        from_attributes = True


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    invoice_date: date
    amount: float
    currency: str
    payment_status: str

    class Config:
        from_attributes = True


class InvoiceConfirmation(BaseModel):
    proposal_id: int = Field(gt=0)
    confirm: bool
