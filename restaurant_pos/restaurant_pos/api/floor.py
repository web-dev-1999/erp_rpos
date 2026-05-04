"""
Floor plan API — serves the full floor canvas to the RPOS frontend.
"""
import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_floors():
    """Return all active floors with their tables and live order summaries."""
    floors = frappe.get_all(
        "POS Floor",
        filters={"is_active": 1},
        fields=["name", "floor_name", "sequence", "background_color", "grid_cols", "grid_rows"],
        order_by="sequence asc",
    )

    # If no floors defined, return a default "virtual" floor with all tables
    if not floors:
        floors = [{"name": "__default__", "floor_name": "Main Floor",
                   "sequence": 1, "background_color": "#f0f2f5",
                   "grid_cols": 20, "grid_rows": 15}]

    table_rows = frappe.db.sql(
        """
        SELECT
            t.name, t.table_number, t.floor_id, t.section_label,
            t.capacity, t.status, t.current_order,
            t.x_pos, t.y_pos, t.width, t.height, t.shape, t.color,
            o.status     AS order_status,
            o.opened_at  AS order_opened_at,
            SUM(oi.amount) AS order_total,
            COUNT(oi.name) AS item_count
        FROM `tabPOS Table` t
        LEFT JOIN `tabPOS Order` o
               ON o.name = t.current_order AND o.status NOT IN ('SETTLED','CLOSED','CANCELLED')
        LEFT JOIN `tabPOS Order Item` oi ON oi.parent = o.name
        WHERE t.is_active = 1
        GROUP BY t.name
        ORDER BY t.table_number ASC
        """,
        as_dict=True,
    )

    # Attach tables to their floor
    floor_map = {f["name"]: f for f in floors}
    for f in floors:
        f["tables"] = []

    for t in table_rows:
        fid = t.get("floor_id") or "__default__"
        if fid not in floor_map:
            fid = floors[0]["name"]
        floor_map[fid]["tables"].append(t)

    # Attach upcoming reservations to tables
    from frappe.utils import now_datetime
    from datetime import timedelta
    now = now_datetime()
    upcoming = frappe.db.sql(
        """
        SELECT name, table_id, guest_name, covers, reservation_datetime, status
        FROM `tabPOS Reservation`
        WHERE status = 'Confirmed'
          AND reservation_datetime BETWEEN %s AND %s
        """,
        (now, now + timedelta(hours=4)),
        as_dict=True,
    )
    res_map = {}
    for r in upcoming:
        res_map.setdefault(r.table_id, []).append(r)

    for f in floors:
        for t in f["tables"]:
            t["reservations"] = res_map.get(t["name"], [])

    return floors


@frappe.whitelist()
def save_table_layout(tables):
    """
    Bulk-save table positions after drag-and-drop in the floor editor.
    ``tables`` is a JSON list: [{name, x_pos, y_pos, width, height, floor_id}]
    """
    import json
    if isinstance(tables, str):
        tables = json.loads(tables)

    for t in tables:
        frappe.db.set_value("POS Table", t["name"], {
            "x_pos":    int(t.get("x_pos", 0)),
            "y_pos":    int(t.get("y_pos", 0)),
            "width":    int(t.get("width", 2)),
            "height":   int(t.get("height", 2)),
            "floor_id": t.get("floor_id"),
        })

    frappe.db.commit()
    return {"saved": len(tables)}


@frappe.whitelist()
def create_table(floor_id, table_number, x_pos=0, y_pos=0, capacity=4, shape="square"):
    """Quick-create a table from the floor editor."""
    if frappe.db.exists("POS Table", table_number):
        frappe.throw(_("Table {0} already exists").format(table_number))

    doc = frappe.new_doc("POS Table")
    doc.table_number = table_number
    doc.floor_id = floor_id
    doc.x_pos = int(x_pos)
    doc.y_pos = int(y_pos)
    doc.capacity = int(capacity)
    doc.shape = shape
    doc.status = "Available"
    doc.is_active = 1
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.as_dict()


@frappe.whitelist()
def get_items_for_pos(pos_profile, item_group=None, search=None):
    """
    Return items for the POS item grid — with image, price, and category.
    Respects the POS Profile's item group filter.
    """
    price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")

    conditions = ["i.disabled = 0", "i.is_sales_item = 1"]
    values = {"price_list": price_list}

    if item_group and item_group != "__all__":
        conditions.append("i.item_group = %(item_group)s")
        values["item_group"] = item_group

    if search:
        conditions.append("(i.item_name LIKE %(search)s OR i.item_code LIKE %(search)s)")
        values["search"] = f"%{search}%"

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            i.name          AS item_code,
            i.item_name,
            i.item_group,
            i.image,
            i.description,
            COALESCE(ip.price_list_rate, 0) AS rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
               ON ip.item_code = i.name
              AND ip.price_list = %(price_list)s
              AND ip.selling = 1
        WHERE {where}
        ORDER BY i.item_group ASC, i.item_name ASC
        LIMIT 300
        """,
        values,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_item_groups_for_pos(pos_profile):
    """Return item groups that have at least one active item."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT i.item_group
        FROM `tabItem` i
        WHERE i.disabled = 0 AND i.is_sales_item = 1
        ORDER BY i.item_group ASC
        """,
        as_dict=True,
    )
    return [r["item_group"] for r in rows if r["item_group"]]
