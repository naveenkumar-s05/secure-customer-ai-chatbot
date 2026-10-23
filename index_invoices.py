from app.database import SessionLocal
from app.models import Invoice
from app.rag import index_invoice, qdrant

db = SessionLocal()

try:
    invoices = db.query(Invoice).all()

    for invoice in invoices:
        index_invoice(invoice)
        print(
            f"Indexed invoice {invoice.invoice_number} "
            f"(customer {invoice.customer_id})"
        )

    print(f"Finished indexing {len(invoices)} invoices.")

finally:
    db.close()
    qdrant.close()