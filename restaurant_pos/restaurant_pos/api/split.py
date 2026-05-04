"""
Bill splitting engine.

Architecture
------------
Splitting operates entirely on POS Orders — no Sales Invoice is involved.

Flow:
  1. start_split(order_name)
       → Parent order → SPLIT_IN_PROGRESS
       → Returns current item list for the UI to present

  2. create_split_plan(order_name, split_config)
       → Validates allocation (no over-allocation, handles partial qty)
       → Creates child POS Orders with assigned items
       → Parent order items that are unassigned remain on a "Remainder" child

  3. finalize_split(order_name)
       → Locks the split; child orders become independently settleable
       → Parent moves to SETTLED when all children are SETTLED

Tax handling
------------
Each child order is settled independently via settlement.create_pos_invoice().
ERPNext's own tax engine (tax_and_charges template from POS Profile) computes
taxes from scratch per invoice.  We never manually distribute tax amounts.
"""

import json
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


# ── Step 1: Initiate split ────────────────────────────────────────────────────

@frappe.whitelist()
def start_split(order_name, client_version=None):
    """
    Transition parent order to SPLIT_IN_PROGRESS and return item list.
    No child orders are created yet — this just locks the order for splitting.
    """
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if order.status in ("SETTLED", "CLOSED", "CANCELLED"):
        frappe.throw(_("Cannot split a {0} order").format(order.status))

    if order.status == "SPLIT_IN_PROGRESS":
        # Already in split — return current state
        return _split_state(order)

    order.status = "SPLIT_IN_PROGRESS"
    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, "split_started", {})
    _publish_global_event("split_started", {"order": order_name})

    return _split_state(order)


# ── Step 2: Create child orders from split plan ───────────────────────────────

@frappe.whitelist()
def create_split_plan(order_name, split_config, client_version=None):
    """
    Validate and materialize a split configuration into child POS Orders.

    ``split_config`` JSON schema::

        {
          "type": "item_split" | "seat_split" | "equal_split",
          "splits": [
            {
              "name": "Bill A",
              "customer": null,          // optional override
              "items": [
                {
                  "item_idx": 3,         // source item .idx
                  "qty": 1               // qty to allocate (<=source qty)
                }
              ]
            }
          ]
        }

    Items not allocated to any split are placed in a system-generated
    "Remainder" split automatically — nothing is lost.
    """
    if isinstance(split_config, str):
        split_config = json.loads(split_config)

    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    if order.status != "SPLIT_IN_PROGRESS":
        frappe.throw(_("Call start_split first"))

    # Cancel any existing children so the plan can be revised
    _cancel_existing_children(order_name)

    _validate_split_config(order, split_config)

    children = []
    allocated = _build_allocation_map(split_config)

    # Create a child order per split
    for split_def in split_config["splits"]:
        child = _create_child_order(order, split_def)
        children.append(child.name)

    # Auto-create Remainder child for unallocated items
    remainder_items = _compute_remainder(order, allocated)
    if remainder_items:
        remainder_def = {
            "name": "Remainder",
            "customer": order.customer,
            "items": remainder_items,
        }
        child = _create_child_order(order, remainder_def)
        children.append(child.name)

    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, "split_plan_created", {"children": children})
    return {"parent": order_name, "children": children}


# ── Step 3: Abort split ───────────────────────────────────────────────────────

@frappe.whitelist()
def abort_split(order_name, client_version=None):
    """
    Cancel all child orders and return parent to COMPLETED state.
    """
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)
    _check_version(order, client_version)

    _cancel_existing_children(order_name)

    order.status = "COMPLETED"
    order.version = (order.version or 0) + 1
    order.save(ignore_permissions=True)
    frappe.db.commit()

    _publish_order_event(order_name, "split_aborted", {})
    return _order_to_dict(order)


# ── Query helpers ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_split_children(order_name):
    children = frappe.get_all(
        "POS Order",
        filters={"parent_order": order_name},
        fields=["name", "status", "customer", "pos_invoice"],
    )
    result = []
    for c in children:
        child_order = frappe.get_doc("POS Order", c["name"])
        d = c.copy()
        d["grand_total"] = sum(flt(i.amount) for i in child_order.items)
        d["items"] = [i.as_dict() for i in child_order.items]
        result.append(d)
    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _split_state(order) -> dict:
    return {
        "order": order.name,
        "status": order.status,
        "version": order.version,
        "items": [
            {
                "idx": i.idx,
                "item_code": i.item_code,
                "item_name": i.item_name,
                "qty": i.qty,
                "rate": i.rate,
                "amount": i.amount,
                "seat_id": i.seat_id,
                "item_status": i.item_status,
            }
            for i in order.items
        ],
    }


def _validate_split_config(order, split_config):
    """Ensure no item is over-allocated across all splits."""
    available = {}
    for item in order.items:
        available[item.idx] = flt(item.qty)

    allocated = {}
    for split in split_config.get("splits", []):
        for item_def in split.get("items", []):
            idx = int(item_def["item_idx"])
            qty = flt(item_def["qty"])

            if idx not in available:
                frappe.throw(
                    _("Item index {0} does not exist in order {1}").format(idx, order.name)
                )
            if qty <= 0:
                frappe.throw(_("Allocated qty must be positive (item idx {0})").format(idx))

            allocated[idx] = allocated.get(idx, 0) + qty

    for idx, alloc_qty in allocated.items():
        avail = available.get(idx, 0)
        if alloc_qty > avail + 0.001:
            item_code = next(
                (i.item_code for i in order.items if i.idx == idx), str(idx)
            )
            frappe.throw(
                _("Item {0} is over-allocated: {1} available, {2} requested").format(
                    item_code, avail, alloc_qty
                )
            )


def _build_allocation_map(split_config) -> dict:
    """idx → total allocated qty"""
    allocated = {}
    for split in split_config.get("splits", []):
        for item_def in split.get("items", []):
            idx = int(item_def["item_idx"])
            allocated[idx] = allocated.get(idx, 0) + flt(item_def["qty"])
    return allocated


def _compute_remainder(order, allocated: dict) -> list:
    remainder = []
    for item in order.items:
        used = flt(allocated.get(item.idx, 0))
        leftover = flt(item.qty) - used
        if leftover > 0.001:
            remainder.append({"item_idx": item.idx, "qty": leftover})
    return remainder


def _create_child_order(parent, split_def: dict):
    child = frappe.new_doc("POS Order")
    child.pos_profile = parent.pos_profile
    child.company = parent.company
    child.table_id = parent.table_id
    child.customer = split_def.get("customer") or parent.customer
    child.status = "OPEN"
    child.version = 0
    child.parent_order = parent.name
    child.opened_by = frappe.session.user
    child.opened_at = now_datetime()
    child.notes = f"Split from {parent.name} — {split_def['name']}"

    for item_def in split_def.get("items", []):
        src = next(
            (i for i in parent.items if i.idx == int(item_def["item_idx"])), None
        )
        if not src:
            continue
        qty = flt(item_def["qty"])
        child.append("items", {
            "item_code": src.item_code,
            "item_name": src.item_name,
            "qty": qty,
            "rate": src.rate,
            "amount": qty * flt(src.rate),
            "seat_id": src.seat_id,
            "kitchen_station": src.kitchen_station,
            "item_status": src.item_status,
            "modifiers": src.modifiers,
            "notes": src.notes,
        })

    child.insert(ignore_permissions=True)
    return child


def _cancel_existing_children(parent_order_name: str):
    existing = frappe.get_all(
        "POS Order",
        filters={"parent_order": parent_order_name, "status": ["!=", "CANCELLED"]},
        fields=["name"],
    )
    for row in existing:
        frappe.db.set_value("POS Order", row["name"], "status", "CANCELLED")
