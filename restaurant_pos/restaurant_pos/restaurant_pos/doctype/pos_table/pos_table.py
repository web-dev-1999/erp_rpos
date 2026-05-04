import frappe
from frappe.model.document import Document


class POSTable(Document):

    def on_update(self):
        _broadcast_floor_plan_update(self.name, self.status)

    def set_occupied(self, order_name: str):
        self.db_set("status", "Occupied")
        self.db_set("current_order", order_name)
        _broadcast_floor_plan_update(self.name, "Occupied")

    def set_available(self):
        self.db_set("status", "Available")
        self.db_set("current_order", None)
        _broadcast_floor_plan_update(self.name, "Available")


def _broadcast_floor_plan_update(table_name: str, status: str):
    frappe.publish_realtime(
        event="rpos_floor_plan_update",
        message={"table": table_name, "status": status},
        room="rpos_floor_plan",
        after_commit=True,
    )
