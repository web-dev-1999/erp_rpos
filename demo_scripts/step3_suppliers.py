"""Step 3: Suppliers & Procurement — 8 vendors with POs, receipts, invoices."""
import frappe
from frappe.utils import today, add_days, flt
import random
import datetime

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
ABBR = frappe.db.get_value("Company", COMPANY, "abbr")
CURRENCY = frappe.db.get_value("Company", COMPANY, "default_currency")  # PKR
WAREHOUSE = "Stores - AD"  # use Stores for raw materials

print(f"  Company: {COMPANY} | Currency: {CURRENCY} | Warehouse: {WAREHOUSE}")

# Get/create Raw Material item group
if not frappe.db.exists("Item Group", "Raw Material"):
    ig = frappe.new_doc("Item Group")
    ig.item_group_name = "Raw Material"
    ig.parent_item_group = "All Item Groups"
    ig.insert(ignore_permissions=True)

SUPPLIERS = [
    {
        "name": "Al-Nour Fresh Produce",
        "group": "Local Supplier",
        "items": [
            ("Tomatoes",     "Kg",  260),
            ("Onions",       "Kg",  150),
            ("Lettuce",      "Kg",  300),
            ("Bell Peppers", "Kg",  450),
            ("Cucumbers",    "Kg",  190),
            ("Lemon",        "Kg",  380),
            ("Garlic",       "Kg",  600),
            ("Parsley",      "Kg",  750),
            ("Mint",         "Kg",  750),
        ],
    },
    {
        "name": "Gulf Meat Traders",
        "group": "Local Supplier",
        "items": [
            ("Chicken Breast",   "Kg", 1800),
            ("Beef Tenderloin",  "Kg", 4200),
            ("Lamb Chops",       "Kg", 4600),
            ("Ground Beef",      "Kg", 2700),
            ("Chicken Wings",    "Kg", 1600),
        ],
    },
    {
        "name": "Blue Ocean Seafood",
        "group": "Local Supplier",
        "items": [
            ("Sea Bass Fillet", "Kg", 5800),
            ("Shrimp",         "Kg", 5000),
            ("Salmon Fillet",  "Kg", 6200),
            ("Squid",          "Kg", 3100),
        ],
    },
    {
        "name": "Golden Grain Foods",
        "group": "Raw Material",
        "items": [
            ("Basmati Rice",    "Kg",  920),
            ("Plain Flour",     "Kg",  380),
            ("Breadcrumbs",     "Kg",  620),
            ("Pasta Penne",     "Kg",  700),
            ("Pasta Spaghetti", "Kg",  700),
        ],
    },
    {
        "name": "Arabian Dairy Co.",
        "group": "Local Supplier",
        "items": [
            ("Fresh Cream",       "Liter", 1400),
            ("Mozzarella Cheese", "Kg",    2700),
            ("Butter",            "Kg",    1950),
            ("Yogurt",            "Kg",     930),
            ("Milk",              "Liter",  460),
        ],
    },
    {
        "name": "Premium Beverage Dist.",
        "group": "Local Supplier",
        "items": [
            ("Cola Can",             "Nos",  310),
            ("Orange Juice Carton",  "Nos",  620),
            ("Water Bottle 500ml",   "Nos",  115),
            ("Mango Juice Carton",   "Nos",  620),
            ("Sparkling Water 330ml","Nos",  230),
        ],
    },
    {
        "name": "Spice Kingdom",
        "group": "Raw Material",
        "items": [
            ("Mixed Spices",      "Kg", 1550),
            ("Cumin",             "Kg", 1150),
            ("Coriander Powder",  "Kg", 1150),
            ("Turmeric",          "Kg",  930),
            ("Paprika",           "Kg", 1390),
            ("Black Pepper",      "Kg", 1550),
        ],
    },
    {
        "name": "Sweet Pantry Supplies",
        "group": "Raw Material",
        "items": [
            ("Sugar",           "Kg",  385),
            ("Cocoa Powder",    "Kg", 1700),
            ("Vanilla Extract", "Liter",2330),
            ("Honey",           "Kg",  1950),
            ("Dates",           "Kg",  1390),
        ],
    },
]

# Supplier groups
for grp in ["Local Supplier", "Raw Material"]:
    if not frappe.db.exists("Supplier Group", grp):
        sg = frappe.new_doc("Supplier Group")
        sg.supplier_group_name = grp
        sg.insert(ignore_permissions=True)

print("\n=== STEP 3: SUPPLIERS & PROCUREMENT ===\n")

# Create suppliers
for s in SUPPLIERS:
    if not frappe.db.exists("Supplier", s["name"]):
        sup = frappe.new_doc("Supplier")
        sup.supplier_name = s["name"]
        sup.supplier_group = s["group"]
        sup.country = "Pakistan"
        sup.insert(ignore_permissions=True)
        print(f"  Created supplier: {s['name']}")
    else:
        print(f"  Existing supplier: {s['name']}")

frappe.db.commit()

# Create raw material items
RAW_ITEMS = {}
for s in SUPPLIERS:
    for item_name, uom, _ in s["items"]:
        item_code = "RM-" + item_name.upper().replace(" ", "-").replace("'", "")
        if not frappe.db.exists("Item", item_code):
            item = frappe.new_doc("Item")
            item.item_code = item_code
            item.item_name = item_name
            item.item_group = "Raw Material"
            item.stock_uom = uom
            item.is_purchase_item = 1
            item.is_sales_item = 0
            item.valuation_method = "FIFO"
            item.insert(ignore_permissions=True)
        RAW_ITEMS[item_name] = {"code": item_code, "uom": uom}

frappe.db.commit()
print(f"  Raw material items ready: {len(RAW_ITEMS)}")

# 3 procurement rounds over 90 days
base_date = datetime.date.today() - datetime.timedelta(days=88)
po_count = 0

for round_num in range(3):
    order_date = base_date + datetime.timedelta(days=round_num * 29)
    receipt_date = order_date + datetime.timedelta(days=2)
    invoice_date = receipt_date + datetime.timedelta(days=1)

    for s in SUPPLIERS:
        sname = s["name"]
        po_items_data = []

        for item_name, uom, base_rate in s["items"]:
            info = RAW_ITEMS.get(item_name)
            if not info:
                continue
            qty = random.randint(15, 60)
            rate = round(base_rate * random.uniform(0.97, 1.03), 0)
            po_items_data.append({
                "item_code": info["code"],
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "schedule_date": str(receipt_date),
                "warehouse": WAREHOUSE,
            })

        try:
            # Purchase Order
            po = frappe.new_doc("Purchase Order")
            po.supplier = sname
            po.company = COMPANY
            po.currency = CURRENCY
            po.transaction_date = str(order_date)
            po.schedule_date = str(receipt_date)
            for pi in po_items_data:
                po.append("items", pi)
            po.insert(ignore_permissions=True)
            po.submit()

            # Purchase Receipt
            pr = frappe.new_doc("Purchase Receipt")
            pr.supplier = sname
            pr.company = COMPANY
            pr.currency = CURRENCY
            pr.posting_date = str(receipt_date)
            for pi in po_items_data:
                pr.append("items", {
                    "item_code": pi["item_code"],
                    "item_name": pi["item_name"],
                    "qty": pi["qty"],
                    "rate": pi["rate"],
                    "uom": pi["uom"],
                    "stock_uom": pi["uom"],
                    "conversion_factor": 1,
                    "warehouse": WAREHOUSE,
                    "purchase_order": po.name,
                })
            pr.insert(ignore_permissions=True)
            pr.submit()

            # Purchase Invoice
            pinv = frappe.new_doc("Purchase Invoice")
            pinv.supplier = sname
            pinv.company = COMPANY
            pinv.currency = CURRENCY
            pinv.posting_date = str(invoice_date)
            pinv.bill_date = str(invoice_date)
            pinv.bill_no = f"INV-{sname[:4].upper()}-R{round_num+1}"
            for pi in po_items_data:
                pinv.append("items", {
                    "item_code": pi["item_code"],
                    "item_name": pi["item_name"],
                    "qty": pi["qty"],
                    "rate": pi["rate"],
                    "uom": pi["uom"],
                    "stock_uom": pi["uom"],
                    "conversion_factor": 1,
                    "warehouse": WAREHOUSE,
                    "purchase_receipt": pr.name,
                })
            pinv.insert(ignore_permissions=True)
            pinv.submit()

            po_count += 1
            print(f"  R{round_num+1} {sname}: PO {po.name}")

        except Exception as e:
            print(f"  ✗ {sname} R{round_num+1}: {str(e)[:120]}")
            frappe.db.rollback()
            frappe.db.begin()

frappe.db.commit()
print(f"\n✓ Step 3 complete: 8 suppliers, {po_count} PO/PR/PINV cycles.\n")
frappe.destroy()
