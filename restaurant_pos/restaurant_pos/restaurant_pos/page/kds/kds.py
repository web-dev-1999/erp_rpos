import frappe


def get_context(context):
    context.no_cache = 1
    context.stations = frappe.get_all(
        "POS Kitchen Station",
        filters={"is_active": 1},
        fields=["name", "station_name", "station_type", "display_color"],
        order_by="station_name asc",
    )
