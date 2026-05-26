"""
Settlement layer — the ONLY place where ERPNext accounting is touched.

Design contract
---------------
- POS Order is the source of truth for operational state.
- This module creates a POS Invoice (ERPNext DocType) per order at payment time.
- Tax computation is 100% delegated to ERPNext's engine via the
  ``taxes_and_charges`` template on the POS Profile — we never manually
  set tax amounts.
- Stock deduction, accounting entries, and loyalty points are all handled
  by ERPNext's POS Invoice submit flow — we do not replicate that logic.

Split settlement
----------------
Each child POS Order settles independently.  The parent order transitions to
SETTLED only when ALL children are settled.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from restaurant_pos.api._helpers import (
    _lock_order,
    _check_version,
    _publish_order_event,
    _publish_global_event,
    _order_to_dict,
)


# ── Main settlement entry point ───────────────────────────────────────────────

@frappe.whitelist()
def settle_order(order_name, payments, client_version=None, opening_entry=None):
    """
    Create and submit a POS Invoice for a completed/split POS Order.

    ``payments`` is a JSON list::

        [
          {"mode_of_payment": "Cash", "amount": 150.00},
          {"mode_of_payment": "Card", "amount": 50.00}
        ]

    Returns the created POS Invoice name.
    """
    import json
    if isinstance(payments, str):
        payments = json.loads(payments)

    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if order.status not in ("COMPLETED", "OPEN", "SENT_TO_KITCHEN",
                             "PARTIALLY_SERVED", "SPLIT_IN_PROGRESS"):
        frappe.throw(_("Order {0} cannot be settled in status {1}").format(
            order_name, order.status
        ))

    if order.pos_invoice:
        frappe.throw(
            _("Order {0} is already settled (invoice {1})").format(
                order_name, order.pos_invoice
            )
        )

    if not order.items:
        frappe.throw(_("Cannot settle an empty order"))

    invoice = _create_pos_invoice(order, payments, opening_entry=opening_entry)

    order.pos_invoice = invoice.name
    order.status = "SETTLED"
    order.closed_at = now_datetime()
    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)

    # If this is a root order, cancel any leftover unsettled children
    # (e.g. an aborted split where the parent is paid directly instead)
    if not order.parent_order:
        _cancel_orphaned_children(order.name)
        _maybe_release_table(order)
    else:
        _maybe_close_parent(order.parent_order)

    frappe.db.commit()

    _publish_order_event(order_name, "order_settled", {"invoice": invoice.name})
    _publish_global_event("order_settled", {
        "order": order_name, "table": order.table_id, "invoice": invoice.name
    })

    return {"order": order_name, "invoice": invoice.name}


@frappe.whitelist()
def get_settlement_preview(order_name, opening_entry=None):
    """
    Return a pre-computed breakdown for the payment dialog.
    Taxes are estimated using the POS Profile template (not finalised yet).
    """
    order = frappe.get_doc("POS Order", order_name)
    profile = frappe.get_doc("POS Profile", order.pos_profile)

    subtotal = sum(flt(i.amount) for i in order.items)

    # Build a temporary invoice to get ERPNext to compute taxes
    tmp = frappe.new_doc("POS Invoice")
    _populate_invoice_header(tmp, order, profile, opening_entry=opening_entry)
    for oi in order.items:
        tmp.append("items", _invoice_item_row(oi))
    tmp.run_method("set_missing_values")
    tmp.run_method("calculate_taxes_and_totals")

    return {
        "subtotal": subtotal,
        "tax_amount": flt(tmp.total_taxes_and_charges),
        "grand_total": flt(tmp.grand_total),
        "taxes": [
            {
                "account_head": t.account_head,
                "description": t.description,
                "tax_amount": flt(t.tax_amount),
            }
            for t in tmp.taxes
        ],
        "items": [
            {
                "item_code": i.item_code,
                "item_name": i.item_name,
                "qty": i.qty,
                "rate": i.rate,
                "amount": i.amount,
            }
            for i in order.items
        ],
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _create_pos_invoice(order, payments: list, opening_entry=None):
    profile = frappe.get_doc("POS Profile", order.pos_profile)

    invoice = frappe.new_doc("POS Invoice")
    _populate_invoice_header(invoice, order, profile, opening_entry=opening_entry)

    for oi in order.items:
        invoice.append("items", _invoice_item_row(oi))

    # Payments
    total_paid = 0
    for pmt in payments:
        invoice.append("payments", {
            "mode_of_payment": pmt["mode_of_payment"],
            "amount": flt(pmt["amount"]),
        })
        total_paid += flt(pmt["amount"])

    invoice.paid_amount = total_paid

    # Let ERPNext calculate everything — taxes, totals, rounding
    invoice.run_method("set_missing_values")
    invoice.run_method("calculate_taxes_and_totals")

    invoice.insert(ignore_permissions=True)
    invoice.submit()

    return invoice


def _populate_invoice_header(invoice, order, profile, opening_entry=None):
    """Copy POS-relevant header fields from profile and order."""
    invoice.pos_profile = order.pos_profile
    invoice.company = order.company
    invoice.customer = order.customer or profile.customer
    if opening_entry:
        invoice.pos_opening_entry = opening_entry
    invoice.is_pos = 1
    invoice.update_stock = profile.update_stock

    if profile.warehouse:
        invoice.set_warehouse = profile.warehouse
    if profile.taxes_and_charges:
        invoice.taxes_and_charges = profile.taxes_and_charges
    if profile.write_off_account:
        invoice.write_off_account = profile.write_off_account
    if profile.write_off_cost_center:
        invoice.write_off_cost_center = profile.write_off_cost_center

    invoice.selling_price_list = profile.selling_price_list
    invoice.currency = frappe.db.get_value("Price List", profile.selling_price_list, "currency")


def _invoice_item_row(oi) -> dict:
    # Warehouse is set at invoice level via set_warehouse; omit here to avoid mismatch
    return {
        "item_code": oi.item_code,
        "item_name": oi.item_name,
        "qty": flt(oi.qty),
        "rate": flt(oi.rate),
    }


def _cancel_orphaned_children(parent_order_name: str):
    """Cancel any unsettled child orders when the parent is settled directly."""
    children = frappe.get_all(
        "POS Order",
        filters={
            "parent_order": parent_order_name,
            "status": ["not in", ["SETTLED", "CLOSED", "CANCELLED"]],
        },
        pluck="name",
    )
    for child_name in children:
        frappe.db.set_value("POS Order", child_name, "status", "CANCELLED")


def _maybe_release_table(order):
    """Release the table if no other open orders are using it."""
    if not order.table_id:
        return

    other_open = frappe.db.count(
        "POS Order",
        {
            "table_id": order.table_id,
            "status": ["not in", ["SETTLED", "CLOSED", "CANCELLED"]],
            "name": ["!=", order.name],
        },
    )
    if not other_open:
        frappe.get_doc("POS Table", order.table_id).set_available()


def _maybe_close_parent(parent_order_name: str):
    """
    Close the parent order when all its children are settled.
    Also releases the table at that point.
    """
    children = frappe.get_all(
        "POS Order",
        filters={"parent_order": parent_order_name},
        fields=["status"],
    )
    if not children:
        return

    all_settled = all(c["status"] in ("SETTLED", "CLOSED", "CANCELLED") for c in children)
    if not all_settled:
        return

    parent = frappe.get_doc("POS Order", parent_order_name)
    parent.status = "CLOSED"
    parent.closed_at = now_datetime()
    parent.save(ignore_permissions=True)

    _maybe_release_table(parent)
    _publish_order_event(parent_order_name, "order_closed", {})
    _publish_global_event("order_closed", {
        "order": parent_order_name, "table": parent.table_id
    })
