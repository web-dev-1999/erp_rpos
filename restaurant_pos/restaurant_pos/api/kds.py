"""
Kitchen Display System API.

The KDS page subscribes to the ``rpos_station_<name>`` realtime room and
receives ``rpos_kitchen_ticket`` events when items are sent from the POS.
Kitchen staff update item statuses here; those updates propagate back to the
waiter's POS view via ``rpos_order_event``.

Item status progression (kitchen side):
  sent → cooking → ready

The waiter closes the loop:
  ready → served  (called from the POS, not the KDS)
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from restaurant_pos.api._helpers import _publish_order_event, _publish_global_event


# ── Queries ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_kitchen_queue(station_name, limit=100):
    """
    Return all non-served items currently routed to this station,
    ordered by sent_at ascending (oldest first).
    """
    rows = frappe.db.sql(
        """
        SELECT
            poi.name          AS item_row_name,
            poi.idx           AS item_idx,
            poi.item_code,
            poi.item_name,
            poi.qty,
            poi.seat_id,
            poi.item_status,
            poi.sent_at,
            poi.notes,
            poi.modifiers,
            po.name           AS order_name,
            po.table_id,
            po.status         AS order_status
        FROM
            `tabPOS Order Item` poi
            JOIN `tabPOS Order` po ON po.name = poi.parent
        WHERE
            poi.kitchen_station = %(station)s
            AND poi.item_status IN ('sent', 'cooking')
            AND po.status NOT IN ('CANCELLED', 'CLOSED')
        ORDER BY
            poi.sent_at ASC
        LIMIT %(limit)s
        """,
        {"station": station_name, "limit": int(limit)},
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_all_stations_queue():
    """Summary count per station — used by manager overview."""
    return frappe.db.sql(
        """
        SELECT
            poi.kitchen_station AS station,
            poi.item_status     AS status,
            COUNT(*)            AS count
        FROM
            `tabPOS Order Item` poi
            JOIN `tabPOS Order` po ON po.name = poi.parent
        WHERE
            poi.item_status IN ('sent', 'cooking')
            AND po.status NOT IN ('CANCELLED', 'CLOSED')
        GROUP BY poi.kitchen_station, poi.item_status
        """,
        as_dict=True,
    )


# ── Status updates ────────────────────────────────────────────────────────────

@frappe.whitelist()
def update_item_status(order_name, item_idx, new_status):
    """
    Kitchen staff updates an item's cooking status.
    Allowed transitions: sent→cooking, cooking→ready
    Waiter side (ready→served) uses mark_item_served().
    """
    _KITCHEN_TRANSITIONS = {
        "sent":    "cooking",
        "cooking": "ready",
    }
    item_idx = int(item_idx)

    order = frappe.get_doc("POS Order", order_name)
    item = _get_item(order, item_idx)

    expected_next = _KITCHEN_TRANSITIONS.get(item.item_status)
    if new_status != expected_next:
        frappe.throw(
            _("Cannot transition item from {0} to {1}").format(item.item_status, new_status)
        )

    item.item_status = new_status
    if new_status == "ready":
        _check_and_update_order_status(order)

    order.save(ignore_permissions=True)
    frappe.db.commit()

    event_map = {"cooking": "item_cooking", "ready": "item_ready"}
    _publish_order_event(order_name, event_map[new_status], {
        "item_idx": item_idx, "item_code": item.item_code
    })

    # Notify the station queue that this item moved
    frappe.publish_realtime(
        event="rpos_item_status_update",
        message={
            "order": order_name,
            "item_idx": item_idx,
            "item_code": item.item_code,
            "new_status": new_status,
            "station": item.kitchen_station,
        },
        room=f"rpos_station_{frappe.scrub(item.kitchen_station or 'General')}",
        after_commit=True,
    )

    return {"order": order_name, "item_idx": item_idx, "status": new_status}


@frappe.whitelist()
def mark_item_served(order_name, item_idx):
    """Waiter marks a 'ready' item as served at the table."""
    item_idx = int(item_idx)

    order = frappe.get_doc("POS Order", order_name)
    item = _get_item(order, item_idx)

    if item.item_status != "ready":
        frappe.throw(
            _("Item must be 'ready' before marking served (currently: {0})").format(
                item.item_status
            )
        )

    item.item_status = "served"
    item.served_at = now_datetime()

    _check_and_update_order_status(order)
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, "item_served", {
        "item_idx": item_idx, "item_code": item.item_code
    })
    return {"order": order_name, "item_idx": item_idx, "status": "served"}


# ── Doc event (hooks.py: POS Order Item on_update) ────────────────────────────

def on_item_status_change(doc, method=None):
    """Triggered by doc_events hook — re-publishes status for late subscribers."""
    if not doc.parent or not doc.item_status:
        return
    frappe.publish_realtime(
        event="rpos_item_status_update",
        message={
            "order": doc.parent,
            "item_idx": doc.idx,
            "item_code": doc.item_code,
            "new_status": doc.item_status,
        },
        doctype="POS Order",
        docname=doc.parent,
        after_commit=True,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_item(order, item_idx: int):
    for item in order.items:
        if item.idx == item_idx:
            return item
    frappe.throw(_("Item index {0} not found in order {1}").format(item_idx, order.name))


def _check_and_update_order_status(order):
    """Promote order status when all items reach served/ready."""
    statuses = {i.item_status for i in order.items}

    if statuses == {"served"}:
        if order.status not in ("SPLIT_IN_PROGRESS", "SETTLED", "CLOSED", "CANCELLED"):
            order.status = "COMPLETED"
    elif "served" in statuses and "ready" in statuses and "cooking" not in statuses and "sent" not in statuses:
        order.status = "COMPLETED"
    elif "served" in statuses or "ready" in statuses:
        if order.status == "SENT_TO_KITCHEN":
            order.status = "PARTIALLY_SERVED"
