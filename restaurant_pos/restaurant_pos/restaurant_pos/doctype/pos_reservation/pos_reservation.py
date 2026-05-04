import frappe
from datetime import timedelta
from frappe.model.document import Document
from frappe.utils import get_datetime, get_datetime_str


class POSReservation(Document):
    def before_save(self):
        if self.reservation_datetime and not self.auto_release_at:
            self.auto_release_at = get_datetime_str(
                get_datetime(self.reservation_datetime) + timedelta(hours=1)
            )
