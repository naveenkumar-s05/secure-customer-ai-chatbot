
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import get_current_customer
from app.database import get_db
from app.models import (
    Customer,
    Conversation,
    Message,
    Invoice,
    PendingInvoiceProposal,
)
from app.schemas import ConversationCreate, MessageCreate, InvoiceConfirmation
from app.assistant import run_assistant
from app.rag import index_invoice


router = APIRouter(prefix="/conversations", tags=["Conversations"])


def owned_conversation(
    conversation_id: int,
    customer_id: int,
    db: Session,
) -> Conversation:
    """Return a conversation only if it belongs to the authenticated customer."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.customer_id == customer_id,
        )
        .first()
    )

    if conversation is None:
        # Same response for a missing conversation and another customer's ID.
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.post("")
def create_conversation(
    body: ConversationCreate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    conversation = Conversation(
        customer_id=customer.id,
        title=body.title,
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "id": conversation.id,
        "title": conversation.title,
    }


@router.get("")
def list_conversations(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.customer_id == customer.id)
        .order_by(Conversation.id.desc())
        .all()
    )

    return [
        {"id": conversation.id, "title": conversation.title}
        for conversation in conversations
    ]


@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    conversation = owned_conversation(
        conversation_id=conversation_id,
        customer_id=customer.id,
        db=db,
    )

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(50)
        .all()
    )
    messages.reverse()

    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        }
        for message in messages
    ]


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: int,
    body: MessageCreate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Save a user message, run the assistant, and return its answer and sources."""
    conversation = owned_conversation(
        conversation_id=conversation_id,
        customer_id=customer.id,
        db=db,
    )

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    try:
        result = run_assistant(
            db=db,
            customer=customer,
            conversation=conversation,
        )
    except Exception:
        # Keep the user's message, but don't expose internal error details.
        raise HTTPException(
            status_code=502,
            detail="The AI assistant could not process your message. Please try again.",
        )

    answer = result.get("answer") or "I couldn't generate an answer."
    sources = result.get("sources", [])
    pending_invoice = result.get("pending_invoice")

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return {
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
        "conversation_id": conversation.id,
        "answer": answer,
        "sources": sources,
        "pending_invoice": pending_invoice,
    }


@router.post("/{conversation_id}/confirm-invoice")
def confirm_invoice(
    conversation_id: int,
    body: InvoiceConfirmation,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """
    Confirm or cancel an invoice proposal.

    The proposal must belong to the authenticated customer and the
    conversation in the URL. A confirmed proposal is inserted into
    PostgreSQL, then indexed in Qdrant.
    """
    conversation = owned_conversation(
        conversation_id=conversation_id,
        customer_id=customer.id,
        db=db,
    )

    proposal = (
        db.query(PendingInvoiceProposal)
        .filter(
            PendingInvoiceProposal.id == body.proposal_id,
            PendingInvoiceProposal.customer_id == customer.id,
            PendingInvoiceProposal.conversation_id == conversation.id,
        )
        .with_for_update()
        .first()
    )

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice proposal not found",
        )

    if proposal.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is already {proposal.status}",
        )

    # Explicit cancellation; no invoice is inserted.
    if not body.confirm:
        proposal.status = "cancelled"
        db.commit()

        return {
            "status": "cancelled",
            "proposal_id": proposal.id,
            "message": "Invoice proposal cancelled. No invoice was created.",
        }

    # Check duplicate number again at confirmation time.
    duplicate = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer.id,
            Invoice.invoice_number == proposal.invoice_number,
        )
        .first()
    )

    if duplicate:
        try:
            proposal.status = "rejected"
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An invoice with this number already exists for your account.",
        )

    invoice = Invoice(
        customer_id=customer.id,
        invoice_number=proposal.invoice_number,
        invoice_date=proposal.invoice_date,
        amount=proposal.amount,
        currency=proposal.currency,
        payment_status=proposal.payment_status,
    )

    try:
        db.add(invoice)
        proposal.status = "confirmed"
        db.commit()
        db.refresh(invoice)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Invoice could not be created; check for a duplicate invoice number.",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Invoice could not be created due to a database error.",
        )

    # PostgreSQL is the source of truth. If indexing fails, the invoice
    # remains created; report that indexing needs recovery.
    try:
        index_invoice(invoice)
        indexing_status = "indexed"
    except Exception:
        indexing_status = "indexing_failed"

    return {
        "status": "created",
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "amount": invoice.amount,
            "currency": invoice.currency,
            "payment_status": invoice.payment_status,
        },
        "indexing_status": indexing_status,
        "message": (
            "Invoice created successfully."
            if indexing_status == "indexed"
            else (
                "Invoice was created in PostgreSQL, but its search index "
                "update failed. Re-index it to make it searchable."
            )
        ),
    }
