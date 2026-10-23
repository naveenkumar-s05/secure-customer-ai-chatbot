
from app.rag import search_records, qdrant


def run_test():
    print("\nCustomer 1 search:")
    results_1 = search_records(1, "Show me my invoices")

    for result in results_1:
        print(result)

    print("\nCustomer 2 search:")
    results_2 = search_records(2, "Show me my invoices")

    for result in results_2:
        print(result)

    # Verify no cross-customer invoice leakage.
    customer_1_ids = {
        result["invoice_number"] for result in results_1
    }
    customer_2_ids = {
        result["invoice_number"] for result in results_2
    }

    assert all(
        invoice.startswith("INV-10")
        for invoice in customer_1_ids
    ), f"Unexpected invoice in customer 1 results: {customer_1_ids}"

    assert all(
        invoice.startswith("INV-20")
        for invoice in customer_2_ids
    ), f"Unexpected invoice in customer 2 results: {customer_2_ids}"

    print("\nPASS: customer search results are separated.")


try:
    run_test()
except Exception as exc:
    print(f"\nRAG test failed: {type(exc).__name__}: {exc}")
    raise
finally:
    qdrant.close()
