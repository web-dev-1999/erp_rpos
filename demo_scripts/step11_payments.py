"""Step 11: Payment reconciliation — create Payment Entries for outstanding invoices."""
import frappe
import random
from frappe.utils import flt

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
CURRENCY = frappe.db.get_value("Company", COMPANY, "default_currency")
DEBTORS = frappe.db.get_value("Account", {"account_type": "Receivable", "company": COMPANY, "is_group": 0}, "name")
CASH_ACCOUNT = "Cash - AD"
BANK_ACCOUNT = "Demo Bank Account - AD"

PAYMENT_MODES = [
    ("Cash",        0.45, CASH_ACCOUNT),
    ("Credit Card", 0.35, BANK_ACCOUNT),
    ("Debit Card",  0.12, BANK_ACCOUNT),
    ("Online",      0.08, BANK_ACCOUNT),
]

print("\n=== STEP 11: PAYMENT ENTRIES ===\n")

# Get unpaid invoices in batches
unpaid = frappe.db.sql("""
    SELECT name, customer, grand_total, outstanding_amount, posting_date
    FROM `tabSales Invoice`
    WHERE docstatus = 1
      AND outstanding_amount > 0
    ORDER BY posting_date ASC
""", as_dict=True)

print(f"  Outstanding invoices to pay: {len(unpaid)}")

paid = 0
failed = 0

for inv in unpaid:
    try:
        # Determine payment mode by invoice remarks (set in step10)
        mode_name = random.choices(
            [m[0] for m in PAYMENT_MODES],
            weights=[m[1] for m in PAYMENT_MODES],
            k=1
        )[0]
        paid_to = next(m[2] for m in PAYMENT_MODES if m[0] == mode_name)
        pay_type = "Cash" if mode_name == "Cash" else "Bank"

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = inv.customer
        pe.company = COMPANY
        pe.posting_date = inv.posting_date
        pe.currency = CURRENCY
        pe.paid_amount = flt(inv.outstanding_amount)
        pe.received_amount = flt(inv.outstanding_amount)
        pe.paid_from = DEBTORS
        pe.paid_to = paid_to
        pe.paid_from_account_currency = CURRENCY
        pe.paid_to_account_currency = CURRENCY
        pe.mode_of_payment = mode_name
        pe.reference_no = inv.name
        pe.reference_date = inv.posting_date

        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": inv.name,
            "allocated_amount": flt(inv.outstanding_amount),
        })

        pe.insert(ignore_permissions=True)
        pe.submit()
        paid += 1

        if paid % 500 == 0:
            frappe.db.commit()
            print(f"  Processed {paid} payments...")

    except Exception as e:
        failed += 1
        frappe.db.rollback()
        frappe.db.begin()

frappe.db.commit()
print(f"\n✓ Step 11 complete: {paid} payments processed, {failed} failed.\n")
frappe.destroy()
