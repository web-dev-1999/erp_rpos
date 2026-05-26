"""
Order lifecycle API — all mutating operations go through here.

Concurrency model
-----------------
Every write takes an explicit row-level lock (SELECT ... FOR UPDATE) then
validates the client-supplied ``version`` matches the DB value.  If not, a
409-style ValidationError is raised so the client can re-fetch and retry.
The ``version`` counter is incremented on every successful write and the
updated order dict is returned so the client stays in sync.

Event publishing
----------------
All ``frappe.publish_realtime`` calls use ``after_commit=True`` so events are
only delivered if the surrounding DB transaction commits successfully.
"""

import json
import frappe
from frappe import _
from frappe.utils import now_datetime, flt, cstr

from restaurant_pos.api._helpers import (
    _lock_order,
    _check_version,
    _publish_order_event,
    _publish_global_event,
    _order_to_dict,
)


# ── Create ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def create_order(pos_profile, table_id=None, customer=None, guest_count=1):
    """Open a new POS Order and mark the table Occupied."""
    profile = frappe.get_doc("POS Profile", pos_profile)

    order = frappe.new_doc("POS Order")
    order.pos_profile = pos_profile
    order.company = profile.company
    order.table_id = table_id
    order.customer = customer
    order.guest_count = int(guest_count)
    order.status = "OPEN"
    order.version = 0
    order.insert(ignore_permissions=True)

    if table_id:
        tbl = frappe.get_doc("POS Table", table_id)
        tbl.set_occupied(order.name)

    frappe.db.commit()

    _publish_global_event("order_created", {"order": order.name, "table": table_id})
    return _order_to_dict(order)


# ── Read ──────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_order(order_name):
    order = frappe.get_doc("POS Order", order_name)
    return _order_to_dict(order)


@frappe.whitelist()
def list_open_orders(pos_profile=None):
    filters = {"status": ["not in", ["CLOSED", "CANCELLED", "SETTLED"]]}
    if pos_profile:
        filters["pos_profile"] = pos_profile

    return frappe.get_all(
        "POS Order",
        filters=filters,
        fields=["name", "table_id", "status", "customer", "opened_at", "version"],
        order_by="opened_at desc",
    )


# ── Item operations ───────────────────────────────────────────────────────────

@frappe.whitelist()
def add_item(order_name, item_code, qty=1, rate=None, seat_id=None,
             modifiers=None, notes=None, client_version=None):
    """
    Add an item to an open order.
    ``rate`` defaults to the item's standard selling price if omitted.
    ``modifiers`` is a JSON-serialisable list, stored as text.
    """
    qty = flt(qty)
    if qty <= 0:
        frappe.throw(_("Quantity must be positive"))

    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if order.status not in ("OPEN", "SENT_TO_KITCHEN", "PARTIALLY_SERVED"):
        frappe.throw(_("Cannot add items to an order in status {0}").format(order.status))

    if rate is None:
        rate = _get_item_rate(item_code, order.pos_profile)

    from restaurant_pos.restaurant_pos.doctype.pos_order.pos_order import _resolve_station
    station = _resolve_station(item_code)

    modifier_json = ""
    if modifiers:
        modifier_json = json.dumps(
            json.loads(modifiers) if isinstance(modifiers, str) else modifiers
        )

    order.append("items", {
        "item_code": item_code,
        "item_name": frappe.db.get_value("Item", item_code, "item_name") or item_code,
        "qty": qty,
        "rate": flt(rate),
        "amount": qty * flt(rate),
        "seat_id": seat_id or "",
        "kitchen_station": station,
        "item_status": "pending",
        "modifiers": modifier_json,
        "notes": notes or "",
    })

    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, "item_added", {
        "item_code": item_code, "qty": qty, "seat": seat_id
    })
    return _order_to_dict(order)


@frappe.whitelist()
def update_item_qty(order_name, item_idx, qty, client_version=None):
    qty = flt(qty)
    if qty < 0:
        frappe.throw(_("Quantity cannot be negative"))

    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    idx = int(item_idx)
    item = _get_item_by_idx(order, idx)

    if item.item_status in ("cooking", "ready", "served"):
        frappe.throw(
            _("Cannot modify item already {0} in kitchen").format(item.item_status)
        )

    if qty == 0:
        order.items = [i for i in order.items if i.idx != idx]
        event = "item_removed"
        event_data = {"item_idx": idx}
    else:
        item.qty = qty
        item.amount = qty * flt(item.rate)
        event = "item_qty_updated"
        event_data = {"item_idx": idx, "qty": qty}

    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, event, event_data)
    return _order_to_dict(order)


@frappe.whitelist()
def remove_item(order_name, item_idx, client_version=None):
    return update_item_qty(order_name, item_idx, 0, client_version)


# ── Kitchen send ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def send_to_kitchen(order_name, item_idxs=None, client_version=None):
    """
    Mark pending items as 'sent' and fire per-station kitchen events.
    ``item_idxs``: JSON list of item idx values to send.  If None, sends all pending.
    """
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if isinstance(item_idxs, str):
        item_idxs = json.loads(item_idxs)

    now = now_datetime()
    sent = []

    for item in order.items:
        if item.item_status != "pending":
            continue
        if item_idxs and item.idx not in item_idxs:
            continue

        item.item_status = "sent"
        item.sent_at = now
        sent.append({
            "item_idx": item.idx,
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "seat_id": item.seat_id,
            "notes": item.notes,
            "modifiers": item.modifiers,
            "kitchen_station": item.kitchen_station,
        })

    if not sent:
        frappe.throw(_("No pending items to send"))

    # Determine new order status
    all_statuses = {i.item_status for i in order.items}
    if "pending" in all_statuses:
        order.status = "SENT_TO_KITCHEN"
    else:
        order.status = "SENT_TO_KITCHEN"

    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    # Group by station and fire one event per station (KDS listens per station)
    by_station = {}
    for s in sent:
        st = s["kitchen_station"] or "General"
        by_station.setdefault(st, []).append(s)

    for station, items in by_station.items():
        frappe.publish_realtime(
            event="rpos_kitchen_ticket",
            message={
                "order": order_name,
                "table": order.table_id,
                "station": station,
                "items": items,
                "sent_at": cstr(now),
            },
            room=f"rpos_station_{frappe.scrub(station)}",
            after_commit=True,
        )

    _publish_order_event(order_name, "items_sent_to_kitchen", {"count": len(sent)})
    return _order_to_dict(order)


# ── Customer ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def set_customer(order_name, customer=None):
    """Assign or clear the customer on an open order."""
    order = frappe.get_doc("POS Order", order_name)
    if order.status in ("SETTLED", "CLOSED", "CANCELLED"):
        frappe.throw(_("Cannot change customer on a {0} order").format(order.status))
    order.customer = customer or None
    order.save(ignore_permissions=True)
    frappe.db.commit()
    return _order_to_dict(order)


# ── Status shortcuts ──────────────────────────────────────────────────────────

@frappe.whitelist()
def mark_completed(order_name, client_version=None):
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)
    order.status = "COMPLETED"
    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()
    _publish_order_event(order_name, "order_completed", {})
    return _order_to_dict(order)


@frappe.whitelist()
def cancel_order(order_name, reason=None, client_version=None):
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if order.status in ("SETTLED", "CLOSED"):
        frappe.throw(_("Cannot cancel a {0} order").format(order.status))

    order.status = "CANCELLED"
    order.notes = (order.notes or "") + f"\nCancelled: {reason or 'No reason given'}"
    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)

    if order.table_id:
        frappe.get_doc("POS Table", order.table_id).set_available()

    frappe.db.commit()
    _publish_order_event(order_name, "order_cancelled", {"reason": reason})
    _publish_global_event("order_cancelled", {"order": order_name, "table": order.table_id})
    return _order_to_dict(order)


# ── Doc event handlers (called from hooks.py) ─────────────────────────────────

def on_order_after_insert(doc, method=None):
    _publish_global_event("order_created", {"order": doc.name, "table": doc.table_id})


def on_order_update(doc, method=None):
    _publish_order_event(doc.name, "order_updated", {"status": doc.status})


def on_order_cancel(doc, method=None):
    if doc.table_id:
        try:
            frappe.get_doc("POS Table", doc.table_id).set_available()
        except Exception:
            pass


# ── Maintenance ───────────────────────────────────────────────────────────────

def cleanup_stale_orders():
    """Mark orders open for more than 24h as CANCELLED (hourly job)."""
    stale = frappe.db.sql(
        """
        SELECT name FROM `tabPOS Order`
        WHERE status IN ('OPEN', 'SENT_TO_KITCHEN', 'PARTIALLY_SERVED')
          AND opened_at < NOW() - INTERVAL 24 HOUR
        """,
        as_dict=True,
    )
    for row in stale:
        try:
            frappe.db.set_value("POS Order", row["name"], {
                "status": "CANCELLED",
                "notes": "Auto-cancelled: stale order",
            })
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Stale order cleanup failed")


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_item_rate(item_code: str, pos_profile: str) -> float:
    price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
    rate = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        "price_list_rate",
    )
    return flt(rate)


def _get_item_by_idx(order, idx: int):
    for item in order.items:
        if item.idx == idx:
            return item
    frappe.throw(_("Item index {0} not found in order").format(idx))
