"""
Reservation management API.

Auto-release flow
-----------------
A scheduler task runs every 15 minutes and finds reservations whose
auto_release_at has passed without the table being seated.  It fires a
realtime notification to the floor plan so the waiter sees an alert badge.
If the table is still unreleased 30 minutes after auto_release_at, the
reservation is automatically marked No-Show and the table reset to Available.
"""
import frappe
from datetime import timedelta
from frappe import _
from frappe.utils import now_datetime, get_datetime, get_datetime_str


@frappe.whitelist()
def get_reservations(date=None, status=None):
    """Return reservations for a given date (defaults to today)."""
    from frappe.utils import today, get_datetime_str
    from datetime import datetime, timedelta

    if not date:
        date = today()

    start = get_datetime_str(datetime.strptime(str(date), "%Y-%m-%d"))
    end   = get_datetime_str(datetime.strptime(str(date), "%Y-%m-%d") + timedelta(days=1))

    filters = {
        "reservation_datetime": ["between", [start, end]],
    }
    if status:
        filters["status"] = status

    return frappe.get_all(
        "POS Reservation",
        filters=filters,
        fields=["name", "guest_name", "phone", "covers", "table_id",
                "reservation_datetime", "status", "source", "notes",
                "pos_order", "auto_release_at"],
        order_by="reservation_datetime asc",
    )


@frappe.whitelist()
def create_reservation(table_id, guest_name, reservation_datetime,
                        covers=2, phone=None, email=None, notes=None, source="Phone"):
    doc = frappe.new_doc("POS Reservation")
    doc.table_id = table_id
    doc.guest_name = guest_name
    doc.reservation_datetime = reservation_datetime
    doc.covers = int(covers)
    doc.phone = phone or ""
    doc.email = email or ""
    doc.notes = notes or ""
    doc.source = source
    doc.status = "Confirmed"
    doc.auto_release_at = get_datetime_str(get_datetime(reservation_datetime) + timedelta(hours=1))
    doc.insert(ignore_permissions=True)

    # Mark table Reserved
    frappe.db.set_value("POS Table", table_id, "status", "Reserved")

    frappe.db.commit()

    _publish_floor_update(table_id, "Reserved")
    return doc.as_dict()


@frappe.whitelist()
def seat_reservation(reservation_name, pos_profile, customer=None):
    """Convert a confirmed reservation into an open POS Order."""
    res = frappe.get_doc("POS Reservation", reservation_name)

    if res.status not in ("Confirmed",):
        frappe.throw(_("Reservation {0} is already {1}").format(reservation_name, res.status))

    # Create the order
    from restaurant_pos.api.order import create_order
    order = frappe.call(
        create_order,
        pos_profile=pos_profile,
        table_id=res.table_id,
        customer=customer or None,
        guest_count=res.covers,
    )

    res.status = "Seated"
    res.pos_order = order["name"]
    res.save(ignore_permissions=True)

    frappe.db.commit()
    return order


@frappe.whitelist()
def cancel_reservation(reservation_name, reason=None):
    res = frappe.get_doc("POS Reservation", reservation_name)
    res.status = "Cancelled"
    if reason:
        res.notes = (res.notes or "") + f"\nCancelled: {reason}"
    res.save(ignore_permissions=True)

    # Release table if no other live reservations
    _maybe_release_reserved_table(res.table_id)
    frappe.db.commit()
    _publish_floor_update(res.table_id, "Available")
    return {"cancelled": reservation_name}


# ── Scheduled task (every 15 min) ────────────────────────────────────────────

def check_reservation_auto_release():
    """Notify waiters about stale reservations; auto-mark No-Show at +30min."""
    now = now_datetime()

    # Notify at auto_release_at
    notify_candidates = frappe.db.sql(
        """
        SELECT name, table_id, guest_name, auto_release_at
        FROM `tabPOS Reservation`
        WHERE status = 'Confirmed'
          AND notified = 0
          AND auto_release_at <= %s
        """,
        (now,),
        as_dict=True,
    )
    for r in notify_candidates:
        frappe.publish_realtime(
            event="rpos_reservation_alert",
            message={
                "reservation": r.name,
                "table": r.table_id,
                "guest": r.guest_name,
                "type": "overdue",
            },
            room="rpos_floor_plan",
            after_commit=True,
        )
        frappe.db.set_value("POS Reservation", r.name, "notified", 1)

    # Auto-mark No-Show at auto_release_at + 30 min
    no_show_cutoff = now - timedelta(minutes=30)
    no_shows = frappe.db.sql(
        """
        SELECT name, table_id
        FROM `tabPOS Reservation`
        WHERE status = 'Confirmed'
          AND notified = 1
          AND auto_release_at <= %s
        """,
        (no_show_cutoff,),
        as_dict=True,
    )
    for r in no_shows:
        frappe.db.set_value("POS Reservation", r.name, "status", "No-Show")
        _maybe_release_reserved_table(r.table_id)
        _publish_floor_update(r.table_id, "Available")

    if notify_candidates or no_shows:
        frappe.db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _maybe_release_reserved_table(table_id):
    """Set table Available if no other confirmed reservations exist for it."""
    if not table_id:
        return
    live = frappe.db.count("POS Reservation", {
        "table_id": table_id,
        "status": "Confirmed",
    })
    if not live:
        current_status = frappe.db.get_value("POS Table", table_id, "status")
        if current_status == "Reserved":
            frappe.db.set_value("POS Table", table_id, {"status": "Available", "current_order": None})


def _publish_floor_update(table_id, status):
    frappe.publish_realtime(
        event="rpos_floor_plan_update",
        message={"table": table_id, "status": status},
        room="rpos_floor_plan",
        after_commit=True,
    )
