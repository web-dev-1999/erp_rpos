import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt


# Valid forward-only status transitions
_TRANSITIONS = {
    "OPEN":              {"SENT_TO_KITCHEN", "SPLIT_IN_PROGRESS", "CANCELLED"},
    "SENT_TO_KITCHEN":   {"PARTIALLY_SERVED", "COMPLETED", "SPLIT_IN_PROGRESS", "CANCELLED"},
    "PARTIALLY_SERVED":  {"COMPLETED", "SPLIT_IN_PROGRESS", "CANCELLED"},
    "COMPLETED":         {"SPLIT_IN_PROGRESS", "SETTLED", "CANCELLED"},
    "SPLIT_IN_PROGRESS": {"SETTLED", "CANCELLED"},
    "SETTLED":           {"CLOSED"},
    "CLOSED":            set(),
    "CANCELLED":         set(),
}


class POSOrder(Document):
    # ── Frappe lifecycle hooks ────────────────────────────────────────────

    def before_insert(self):
        self.opened_by = frappe.session.user
        self.opened_at = now_datetime()
        if not self.version:
            self.version = 0

    def validate(self):
        self._validate_status_transition()
        self._compute_item_amounts()
        self._auto_route_items()

    def before_save(self):
        if self.status in ("CLOSED", "SETTLED", "CANCELLED") and not self.closed_at:
            self.closed_at = now_datetime()

    # ── Validation helpers ────────────────────────────────────────────────

    def _validate_status_transition(self):
        if self.is_new():
            return
        previous = frappe.db.get_value("POS Order", self.name, "status")
        if previous == self.status:
            return
        allowed = _TRANSITIONS.get(previous, set())
        if self.status not in allowed:
            frappe.throw(
                _("Status cannot change from {0} to {1}").format(previous, self.status),
                frappe.ValidationError,
            )

    def _compute_item_amounts(self):
        for item in self.items:
            item.amount = flt(item.qty) * flt(item.rate)

    def _auto_route_items(self):
        """Assign kitchen_station to items that don't have one yet."""
        for item in self.items:
            if not item.kitchen_station:
                item.kitchen_station = _resolve_station(item.item_code)

    # ── Convenience properties ────────────────────────────────────────────

    @property
    def grand_total(self):
        return sum(flt(i.amount) for i in self.items)

    def get_pending_items(self):
        return [i for i in self.items if i.item_status == "pending"]

    def get_items_by_station(self):
        grouped = {}
        for item in self.items:
            station = item.kitchen_station or "General"
            grouped.setdefault(station, []).append(item)
        return grouped


# ── Module-level helper ───────────────────────────────────────────────────────

def _resolve_station(item_code: str) -> str:
    """Return the kitchen station name for an item, falling back to default."""
    item_group = frappe.db.get_value("Item", item_code, "item_group")
    station = frappe.db.get_value(
        "POS Item Routing",
        {"item_group": item_group, "is_active": 1},
        "kitchen_station",
        order_by="priority asc",
    )
    if not station:
        station = frappe.db.get_value(
            "POS Kitchen Station", {"is_default": 1, "is_active": 1}, "name"
        )
    return station or ""
