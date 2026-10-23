
from datetime import date

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Customer, Invoice

CUSTOMERS = [
    {
        "name": "Dhoni",
        "mobile": "+917777777777",
        "invoices": [
            ("INV-101", date(2026, 10, 1), 2500, "INR", "unpaid"),
            ("INV-102", date(2026, 10, 3), 1800, "INR", "paid"),
            ("INV-103", date(2026, 10, 5), 4200, "INR", "unpaid"),
            ("INV-104", date(2026, 10, 8), 900, "INR", "paid"),
            ("INV-105", date(2026, 10, 10), 1250, "INR", "unpaid"),
        ],
    },
    {
        "name": "Kohli",
        "mobile": "+911818181818",
        "invoices": [
            ("INV-201", date(2026, 10, 2), 1500, "INR", "paid"),
            ("INV-202", date(2026, 10, 4), 3200, "INR", "unpaid"),
            ("INV-203", date(2026, 10, 6), 750, "INR", "paid"),
            ("INV-204", date(2026, 10, 9), 5600, "INR", "unpaid"),
            ("INV-205", date(2026, 10, 11), 2100, "INR", "paid"),
        ],
    },
]


def seed_customer(db: Session, data: dict):
    customer = (
        db.query(Customer)
        .filter_by(mobile=data["mobile"])
        .first()
    )

    if not customer:
        customer = Customer(
            name=data["name"],
            mobile=data["mobile"],
        )
        db.add(customer)
        db.flush()

    for number, invoice_date, amount, currency, status in data["invoices"]:
        exists = (
            db.query(Invoice)
            .filter_by(
                customer_id=customer.id,
                invoice_number=number,
            )
            .first()
        )

        if not exists:
            db.add(
                Invoice(
                    customer_id=customer.id,
                    invoice_number=number,
                    invoice_date=invoice_date,
                    amount=amount,
                    currency=currency,
                    payment_status=status,
                )
            )

    print(f"Seeded customer: {customer.name} (ID {customer.id})")


def main():
    db = SessionLocal()
    try:
        for data in CUSTOMERS:
            seed_customer(db, data)

        db.commit()
        print("Seed data committed successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
