
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    mobile: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    invoices = relationship("Invoice", back_populates="customer")
    conversations = relationship("Conversation", back_populates="customer")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "invoice_number",
            name="uq_customer_invoice_number",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(80))
    invoice_date: Mapped[datetime.date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    payment_status: Mapped[str] = mapped_column(String(20))

    customer = relationship("Customer", back_populates="invoices")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer = relationship("Customer", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class OTPChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_mobile_created", "mobile", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mobile: Mapped[str] = mapped_column(String(20), index=True)
    otp_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class PendingInvoiceProposal(Base):
    __tablename__ = "pending_invoice_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )

    invoice_number: Mapped[str] = mapped_column(String(80))
    invoice_date: Mapped[datetime.date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")

    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)