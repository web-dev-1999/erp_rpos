"""
Shared utilities used across all API modules.
"""

import frappe
from frappe import _
from frappe.utils import flt, cstr


def _lock_order(order_name: str):
    """
    Acquire a row-level write lock on the POS Order row.
    Must be called before read-modify-write cycles.
    Frappe wraps each request in a transaction, so the lock is held
    until commit/rollback at end of request.
    """
    frappe.db.sql(
        "SELECT name FROM `tabPOS Order` WHERE name = %s FOR UPDATE",
        (order_name,),
    )


def _check_version(order, client_version):
    """
    Optimistic concurrency guard.
    Raises ValidationError if the client's version is stale.
    The client must re-fetch the order and retry.
    """
    if client_version is None:
        return
    if int(client_version) != int(order.version or 0):
        frappe.throw(
            _(
                "Order {0} was modified by another session (expected version {1}, "
                "got {2}). Please refresh and try again."
            ).format(order.name, order.version, client_version),
            frappe.ValidationError,
            title=_("Version Conflict"),
        )


def _publish_order_event(order_name: str, event_type: str, data: dict):
    """Publish an event scoped to a single order (clients subscribed to that order)."""
    frappe.publish_realtime(
        event="rpos_order_event",
        message={
            "order": order_name,
            "type": event_type,
            "data": data,
        },
        doctype="POS Order",
        docname=order_name,
        after_commit=True,
    )


def _publish_global_event(event_type: str, data: dict):
    """Publish a global event to the floor plan / manager view."""
    frappe.publish_realtime(
        event="rpos_global",
        message={"type": event_type, **data},
        room="rpos_floor_plan",
        after_commit=True,
    )


def _order_to_dict(order) -> dict:
    """Serialize a POS Order document to a clean dict for API responses."""
    d = order.as_dict()
    d["grand_total"] = sum(flt(i["amount"]) for i in d.get("items", []))
    return d
