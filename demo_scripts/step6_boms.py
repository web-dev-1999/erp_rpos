"""Step 6: Manufacturing/Recipes — BOMs for key menu items + Work Orders for initial stock."""
import frappe
import datetime

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
WAREHOUSE = "Stores - AD"
FG_WAREHOUSE = "Finished Goods - AD"
WIP_WAREHOUSE = "Work In Progress - AD"

# BOM definitions: (finished_item_code, [(raw_material_code, qty_kg_or_nos)])
BOMS = [
    ("FOOD-MN-001",  # Grilled Chicken Breast
     [("RM-CHICKEN-BREAST", 0.3), ("RM-GARLIC", 0.02), ("RM-MIXED-SPICES", 0.01),
      ("RM-LEMON", 0.05), ("RM-BELL-PEPPERS", 0.1)]),

    ("FOOD-MN-002",  # Beef Tenderloin Steak
     [("RM-BEEF-TENDERLOIN", 0.35), ("RM-BUTTER", 0.03), ("RM-GARLIC", 0.02),
      ("RM-BLACK-PEPPER", 0.005), ("RM-MIXED-SPICES", 0.01)]),

    ("FOOD-MN-003",  # Lamb Chops
     [("RM-LAMB-CHOPS", 0.4), ("RM-GARLIC", 0.02), ("RM-MIXED-SPICES", 0.02),
      ("RM-LEMON", 0.05), ("RM-CORIANDER-POWDER", 0.01)]),

    ("FOOD-MN-004",  # Grilled Sea Bass
     [("RM-SEA-BASS-FILLET", 0.35), ("RM-LEMON", 0.05), ("RM-GARLIC", 0.02),
      ("RM-MIXED-SPICES", 0.01), ("RM-BUTTER", 0.02)]),

    ("FOOD-MN-005",  # Shrimp Pasta
     [("RM-SHRIMP", 0.2), ("RM-PASTA-PENNE", 0.15), ("RM-FRESH-CREAM", 0.1),
      ("RM-GARLIC", 0.02), ("RM-TOMATOES", 0.1)]),

    ("FOOD-MN-006",  # Chicken Biryani
     [("RM-CHICKEN-BREAST", 0.25), ("RM-BASMATI-RICE", 0.2), ("RM-ONIONS", 0.1),
      ("RM-MIXED-SPICES", 0.02), ("RM-YOGURT", 0.08)]),

    ("FOOD-MN-007",  # Beef Burger
     [("RM-GROUND-BEEF", 0.2), ("RM-PLAIN-FLOUR", 0.05), ("RM-TOMATOES", 0.05),
      ("RM-LETTUCE", 0.03), ("RM-ONIONS", 0.05)]),

    ("FOOD-MN-009",  # Margherita Pizza
     [("RM-PLAIN-FLOUR", 0.25), ("RM-MOZZARELLA-CHEESE", 0.15), ("RM-TOMATOES", 0.1),
      ("RM-GARLIC", 0.01), ("RM-MIXED-SPICES", 0.005)]),

    ("FOOD-MN-010",  # Chicken Alfredo Pasta
     [("RM-CHICKEN-BREAST", 0.2), ("RM-PASTA-SPAGHETTI", 0.15), ("RM-FRESH-CREAM", 0.15),
      ("RM-MOZZARELLA-CHEESE", 0.08), ("RM-GARLIC", 0.02)]),

    ("FOOD-ST-001",  # Hummus with Pita Bread
     [("RM-PLAIN-FLOUR", 0.15), ("RM-GARLIC", 0.02), ("RM-LEMON", 0.05),
      ("RM-MIXED-SPICES", 0.01)]),

    ("FOOD-DS-001",  # Chocolate Lava Cake
     [("RM-PLAIN-FLOUR", 0.08), ("RM-COCOA-POWDER", 0.05), ("RM-BUTTER", 0.05),
      ("RM-SUGAR", 0.06), ("RM-MILK", 0.05)]),

    ("FOOD-DS-002",  # Kunafa
     [("RM-PLAIN-FLOUR", 0.15), ("RM-MOZZARELLA-CHEESE", 0.2), ("RM-BUTTER", 0.05),
      ("RM-SUGAR", 0.08), ("RM-HONEY", 0.03)]),
]

print("\n=== STEP 6: BOMs ===\n")

bom_names = {}
created = 0

for item_code, raw_materials in BOMS:
    if frappe.db.exists("BOM", {"item": item_code, "is_active": 1, "is_default": 1}):
        bom_name = frappe.db.get_value("BOM", {"item": item_code, "is_default": 1}, "name")
        bom_names[item_code] = bom_name
        print(f"  Existing BOM for {item_code}: {bom_name}")
        continue

    try:
        bom = frappe.new_doc("BOM")
        bom.item = item_code
        bom.quantity = 1
        bom.company = COMPANY
        bom.is_active = 1
        bom.is_default = 1
        bom.currency = frappe.db.get_value("Company", COMPANY, "default_currency")

        for rm_code, qty in raw_materials:
            # Check if raw material exists
            if not frappe.db.exists("Item", rm_code):
                print(f"    ✗ Raw material not found: {rm_code}")
                continue
            bom.append("items", {
                "item_code": rm_code,
                "item_name": frappe.db.get_value("Item", rm_code, "item_name"),
                "qty": qty,
                "uom": frappe.db.get_value("Item", rm_code, "stock_uom"),
                "stock_uom": frappe.db.get_value("Item", rm_code, "stock_uom"),
                "rate": frappe.db.get_value("Item", rm_code, "valuation_rate") or 0,
                "source_warehouse": WAREHOUSE,
            })

        bom.insert(ignore_permissions=True)
        bom.submit()
        bom_names[item_code] = bom.name
        created += 1
        print(f"  ✓ BOM {bom.name}: {item_code} ({len(raw_materials)} ingredients)")

    except Exception as e:
        print(f"  ✗ BOM for {item_code}: {e}")
        frappe.db.rollback()
        frappe.db.begin()

frappe.db.commit()

# Create Work Orders to produce initial stock (50 portions of each)
print("\n  Creating Work Orders for initial stock...\n")

wo_created = 0
prod_date = str(datetime.date.today() - datetime.timedelta(days=85))

for item_code, bom_name in bom_names.items():
    try:
        wo = frappe.new_doc("Work Order")
        wo.production_item = item_code
        wo.bom_no = bom_name
        wo.qty = 50
        wo.company = COMPANY
        wo.planned_start_date = prod_date
        wo.fg_warehouse = FG_WAREHOUSE
        wo.wip_warehouse = WIP_WAREHOUSE
        wo.insert(ignore_permissions=True)
        wo.submit()

        # Stock Entry to complete the Work Order
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        se_doc = make_stock_entry(wo.name, "Manufacture", 50)
        se_doc.posting_date = prod_date
        se_doc.insert(ignore_permissions=True)
        se_doc.submit()

        wo_created += 1
        print(f"  ✓ WO + SE for {item_code}: 50 portions")

    except Exception as e:
        print(f"  ✗ WO for {item_code}: {str(e)[:100]}")
        frappe.db.rollback()
        frappe.db.begin()

frappe.db.commit()
print(f"\n✓ Step 6 complete: {created} BOMs, {wo_created} Work Orders.\n")
frappe.destroy()
