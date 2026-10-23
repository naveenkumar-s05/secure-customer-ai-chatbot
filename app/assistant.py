import json
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import OLLAMA_URL, OLLAMA_CHAT_MODEL
from app.models import (
    Customer,
    Conversation,
    Message,
    Invoice,
    PendingInvoiceProposal,
)
from app.rag import search_records


MAX_TOOL_ROUNDS = 3
MAX_HISTORY_MESSAGES = 12
RECORD_SEARCH_LIMIT = 10


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_records",
            "description": (
                "Search the authenticated customer's invoices and records. "
                "Use this for questions about existing invoices."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the customer's records",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_invoice",
            "description": (
                "Propose a new invoice for the authenticated customer. "
                "This creates a preview only; it does not save the invoice."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string"},
                    "invoice_date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "amount": {"type": "number"},
                    "currency": {
                        "type": "string",
                        "description": "Three-letter currency code, e.g. INR",
                    },
                    "payment_status": {
                        "type": "string",
                        "enum": ["paid", "unpaid", "overdue"],
                    },
                },
                "required": [
                    "invoice_number",
                    "invoice_date",
                    "amount",
                    "currency",
                    "payment_status",
                ],
            },
        },
    },
]


def _validate_invoice_args(args: dict[str, Any]) -> dict[str, Any]:
    invoice_number = str(args.get("invoice_number", "")).strip()
    if not invoice_number or len(invoice_number) > 80:
        raise ValueError("Invoice number must be 1–80 characters.")

    invoice_date = date.fromisoformat(str(args.get("invoice_date", "")))

    amount = float(args.get("amount", 0))
    if amount <= 0 or amount > 100_000_000:
        raise ValueError(
            "Invoice amount must be positive and within the allowed limit."
        )

    currency = str(args.get("currency", "INR")).upper().strip()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a three-letter code.")

    payment_status = str(args.get("payment_status", "")).lower().strip()
    if payment_status not in {"paid", "unpaid", "overdue"}:
        raise ValueError("Invalid payment status.")

    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "amount": amount,
        "currency": currency,
        "payment_status": payment_status,
    }


def _create_invoice_proposal(
    db: Session,
    customer: Customer,
    conversation: Conversation,
    args: dict[str, Any],
) -> dict[str, Any]:
    values = _validate_invoice_args(args)

    # Check duplicates only within this authenticated customer's account.
    duplicate = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer.id,
            Invoice.invoice_number == values["invoice_number"],
        )
        .first()
    )

    if duplicate:
        return {
            "error": (
                f"Invoice number {values['invoice_number']} already exists "
                "for this customer."
            )
        }

    pending = (
        db.query(PendingInvoiceProposal)
        .filter(
            PendingInvoiceProposal.customer_id == customer.id,
            PendingInvoiceProposal.invoice_number == values["invoice_number"],
            PendingInvoiceProposal.status == "pending",
        )
        .first()
    )

    if pending:
        return {
            "error": (
                f"A pending proposal already exists for invoice "
                f"{values['invoice_number']}."
            )
        }

    proposal = PendingInvoiceProposal(
        customer_id=customer.id,
        conversation_id=conversation.id,
        **values,
        status="pending",
    )

    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    return {
        "proposal_id": proposal.id,
        "preview": {
            "invoice_number": proposal.invoice_number,
            "invoice_date": proposal.invoice_date.isoformat(),
            "amount": proposal.amount,
            "currency": proposal.currency,
            "payment_status": proposal.payment_status,
        },
        "requires_confirmation": True,
        "message": (
            "Invoice preview prepared. Ask the customer to review it and "
            "explicitly confirm before creating the invoice."
        ),
    }


def _execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: Session,
    customer: Customer,
    conversation: Conversation,
) -> dict[str, Any]:
    if tool_name == "search_records":
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"error": "Search query cannot be empty."}

        # Never accept customer_id from the model's tool arguments.
        return {
            "records": search_records(
                customer_id=customer.id,
                query=query,
                limit=RECORD_SEARCH_LIMIT,
            )
        }

    if tool_name == "add_invoice":
        return _create_invoice_proposal(
            db=db,
            customer=customer,
            conversation=conversation,
            args=arguments,
        )

    return {"error": "Tool is not permitted."}


def _is_general_invoice_list_request(user_text: str) -> bool:
    """
    Match natural variations such as:
    - Show me my invoices
    - Show my invoices
    - List all my invoices
    - Can you display my invoices?
    """
    text = " ".join(user_text.lower().split())

    asks_to_list = any(
        word in text for word in ("show", "list", "view", "display")
    )
    refers_to_customer = any(
        word in text for word in ("my", "me", "all")
    )
    mentions_invoice = "invoice" in text or "invoices" in text

    return asks_to_list and refers_to_customer and mentions_invoice


def _format_invoice_records(records: list[dict[str, Any]]) -> str:
    lines = []

    for record in records:
        invoice_number = record.get("invoice_number") or "Invoice"
        record_text = record.get("text") or ""

        # Avoid printing an empty bullet if a record lacks text.
        if record_text:
            lines.append(f"- **{invoice_number}**: {record_text}")
        else:
            lines.append(f"- **{invoice_number}**")

    return "\n".join(lines)


def run_assistant(
    db: Session,
    customer: Customer,
    conversation: Conversation,
) -> dict[str, Any]:
    """Run the assistant for a conversation owned by the authenticated customer."""

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    history.reverse()

    last_user_message = next(
        (
            item.content
            for item in reversed(history)
            if item.role == "user"
        ),
        "",
    )

    user_text = last_user_message.lower()

    # Pre-search records server-side for questions about invoices or payments.
    record_keywords = (
        "invoice",
        "invoices",
        "bill",
        "bills",
        "payment",
        "payments",
        "record",
        "records",
        "paid",
        "unpaid",
        "overdue",
    )

    preloaded_records: list[dict[str, Any]] = []

    if any(keyword in user_text for keyword in record_keywords):
        try:
            preloaded_records = search_records(
                customer_id=customer.id,
                query=last_user_message,
                limit=RECORD_SEARCH_LIMIT,
            )
        except Exception:
            # Keep internal retrieval details out of the user-facing response.
            preloaded_records = []

    all_sources: list[dict[str, Any]] = list(preloaded_records)
    pending_invoice: dict[str, Any] | None = None

    print("DEBUG: latest user message:", repr(last_user_message))
    print("DEBUG: invoice-list match:", _is_general_invoice_list_request(user_text))
    # Handle broad invoice-list requests from retrieved data directly.
    if _is_general_invoice_list_request(user_text):
        print("DEBUG: entered invoice-list branch")
        print("DEBUG: preloaded records:", len(preloaded_records))
        print(
            "DEBUG: invoice numbers:",
            [r.get("invoice_number") for r in preloaded_records],
        )
        if preloaded_records:
            invoice_lines = _format_invoice_records(preloaded_records)

            return {
                "answer": (
                    "Here are the invoices I found in your account:\n\n"
                    f"{invoice_lines}"
                ),
                "sources": all_sources,
                "pending_invoice": None,
            }

        return {
            "answer": (
                "I couldn't find any matching invoices in your account. "
                "You can try asking about a specific invoice number."
            ),
            "sources": [],
            "pending_invoice": None,
        }

    retrieved_context = ""
    if preloaded_records:
        retrieved_context = (
            "\n\nServer-retrieved records for the authenticated customer:\n"
            + json.dumps(preloaded_records, ensure_ascii=False)
            + "\nUse these records to answer the customer's question. "
            "Mention invoice numbers and relevant details. "
            "Do not claim no invoices were found when records are present."
        )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a secure customer invoice assistant. "
                "Answer using the authenticated customer's records. "
                "Use search_records for record questions when more retrieval "
                "is needed. Never claim a record exists unless retrieved data "
                "confirms it. You may propose invoices using add_invoice, but "
                "this only creates a preview. Never claim an invoice was saved "
                "until the server confirms it. Never ask for or use another "
                "customer's records. Keep answers concise. When using retrieved "
                "records, mention invoice numbers and source IDs where helpful."
                + retrieved_context
            ),
        }
    ]

    for item in history:
        if item.role in {"user", "assistant"}:
            messages.append(
                {
                    "role": item.role,
                    "content": item.content,
                }
            )

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_CHAT_MODEL,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
            },
            timeout=180.0,
        )
        response.raise_for_status()

        assistant_message = response.json().get("message", {})
        tool_calls = assistant_message.get("tool_calls") or []

        if not tool_calls:
            return {
                "answer": assistant_message.get("content", "").strip(),
                "sources": all_sources,
                "pending_invoice": pending_invoice,
            }

        messages.append(assistant_message)

        for call in tool_calls:
            function = call.get("function", {})
            tool_name = function.get("name", "")
            raw_arguments = function.get("arguments", {})

            if isinstance(raw_arguments, str):
                try:
                    raw_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    raw_arguments = {}

            try:
                result = _execute_tool(
                    tool_name=tool_name,
                    arguments=raw_arguments,
                    db=db,
                    customer=customer,
                    conversation=conversation,
                )
            except (ValueError, TypeError) as exc:
                result = {"error": str(exc)}
            except Exception:
                result = {"error": "The requested tool operation failed."}

            if tool_name == "search_records":
                all_sources.extend(result.get("records", []))

            if (
                tool_name == "add_invoice"
                and result.get("requires_confirmation")
            ):
                pending_invoice = result

            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return {
        "answer": (
            "I couldn't complete the request within the allowed tool-call "
            "steps. Please try a more specific question."
        ),
        "sources": all_sources,
        "pending_invoice": pending_invoice,
    }