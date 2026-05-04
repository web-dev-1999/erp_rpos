"""Step 8: Floor Plan & Table Setup — 3 floors with tables."""
import frappe

frappe.init(site="frontend")
frappe.connect()

FLOORS = [
    {
        "name": "Main Dining",
        "sequence": 1,
        "background_color": "#f5f0e8",
        "grid_cols": 20,
        "grid_rows": 15,
        "tables": [
            # (number, x, y, w, h, capacity, shape)
            (1,  1,  1, 3, 2,  4, "square"),
            (2,  5,  1, 3, 2,  4, "square"),
            (3,  9,  1, 3, 2,  4, "square"),
            (4, 13,  1, 3, 2,  4, "square"),
            (5,  1,  4, 4, 2,  6, "square"),
            (6,  6,  4, 4, 2,  6, "square"),
            (7, 11,  4, 4, 2,  6, "square"),
            (8,  1,  7, 5, 3,  8, "square"),
            (9,  7,  7, 5, 3,  8, "square"),
            (10,13,  7, 5, 3, 10, "square"),
        ],
    },
    {
        "name": "Terrace",
        "sequence": 2,
        "background_color": "#e8f5e9",
        "grid_cols": 20,
        "grid_rows": 12,
        "tables": [
            (11, 1, 1, 3, 2, 2, "round"),
            (12, 5, 1, 3, 2, 2, "round"),
            (13, 9, 1, 3, 2, 2, "round"),
            (14, 1, 4, 3, 2, 4, "round"),
            (15, 5, 4, 3, 2, 4, "round"),
            (16, 9, 4, 3, 2, 4, "round"),
            (17, 1, 7, 4, 2, 6, "round"),
            (18, 6, 7, 4, 2, 6, "round"),
        ],
    },
    {
        "name": "Private Dining",
        "sequence": 3,
        "background_color": "#ede7f6",
        "grid_cols": 16,
        "grid_rows": 10,
        "tables": [
            (19, 1, 1, 5, 3,  8, "square"),
            (20, 7, 1, 5, 3, 12, "square"),
            (21, 1, 5, 5, 3, 10, "square"),
            (22, 7, 5, 5, 3, 14, "square"),
        ],
    },
]

print("\n=== STEP 8: FLOOR PLAN & TABLES ===\n")

floors_created = 0
tables_created = 0

for floor_data in FLOORS:
    floor_name = floor_data["name"]

    # Create or get floor
    if frappe.db.exists("POS Floor", floor_name):
        floor = frappe.get_doc("POS Floor", floor_name)
        print(f"  Existing floor: {floor_name}")
    else:
        floor = frappe.new_doc("POS Floor")
        floor.floor_name = floor_name
        floor.sequence = floor_data["sequence"]
        floor.background_color = floor_data["background_color"]
        floor.grid_cols = floor_data["grid_cols"]
        floor.grid_rows = floor_data["grid_rows"]
        floor.is_active = 1
        floor.insert(ignore_permissions=True)
        floors_created += 1
        print(f"  ✓ Floor: {floor_name} (id: {floor.name})")

    floor_id = floor.name

    for (tnum, x, y, w, h, cap, shape) in floor_data["tables"]:
        table_number = str(tnum)
        if frappe.db.exists("POS Table", {"table_number": table_number}):
            print(f"    Table {tnum}: exists")
            continue

        table = frappe.new_doc("POS Table")
        table.table_number = table_number
        table.floor_id = floor_id
        table.x_pos = x
        table.y_pos = y
        table.width = w
        table.height = h
        table.capacity = cap
        table.shape = shape
        table.status = "Available"
        table.is_active = 1
        table.insert(ignore_permissions=True)
        tables_created += 1

    print(f"    Tables for {floor_name}: {len(floor_data['tables'])}")

frappe.db.commit()
print(f"\n✓ Step 8 complete: {floors_created} floors, {tables_created} tables.\n")
frappe.destroy()
