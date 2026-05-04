"""Step 7: Inventory Setup — populate warehouses with realistic stock levels."""
import frappe
import datetime

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
STORES = "Stores - AD"
FG = "Finished Goods - AD"
OPENING_DATE = str(datetime.date.today() - datetime.timedelta(days=92))

print("\n=== STEP 7: INVENTORY SETUP ===\n")


def make_material_receipt(warehouse, items_data, entry_date, purpose="Material Receipt"):
    """Create a Stock Entry of type Material Receipt."""
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = purpose
    se.purpose = purpose
    se.company = COMPANY
    se.posting_date = entry_date
    se.posting_time = "08:00:00"

    for item_code, qty, valuation_rate in items_data:
        se.append("items", {
            "item_code": item_code,
            "qty": qty,
            "t_warehouse": warehouse,
            "basic_rate": valuation_rate,
            "valuation_rate": valuation_rate,
        })

    se.insert(ignore_permissions=True)
    se.submit()
    return se.name


# --- 1. Raw Materials in Stores ---
# Stock levels: 4x weekly usage (buffer for 90-day simulation)
RAW_MATERIAL_STOCK = [
    # (item_code, qty, valuation_rate_per_unit)
    # Produce
    ("RM-TOMATOES",      200,  260),
    ("RM-ONIONS",        150,  150),
    ("RM-LETTUCE",       100,  300),
    ("RM-BELL-PEPPERS",   80,  450),
    ("RM-CUCUMBERS",     100,  190),
    ("RM-LEMON",          80,  380),
    ("RM-GARLIC",         50,  600),
    ("RM-PARSLEY",        30,  750),
    ("RM-MINT",           30,  750),
    # Meat
    ("RM-CHICKEN-BREAST",150, 1800),
    ("RM-BEEF-TENDERLOIN",80, 4200),
    ("RM-LAMB-CHOPS",     60, 4600),
    ("RM-GROUND-BEEF",   100, 2700),
    ("RM-CHICKEN-WINGS",  80, 1600),
    # Seafood
    ("RM-SEA-BASS-FILLET",50, 5800),
    ("RM-SHRIMP",         60, 5000),
    ("RM-SALMON-FILLET",  40, 6200),
    ("RM-SQUID",          40, 3100),
    # Grains
    ("RM-BASMATI-RICE",  200,  920),
    ("RM-PLAIN-FLOUR",   300,  380),
    ("RM-BREADCRUMBS",   100,  620),
    ("RM-PASTA-PENNE",   120,  700),
    ("RM-PASTA-SPAGHETTI",120, 700),
    # Dairy
    ("RM-FRESH-CREAM",    80, 1400),
    ("RM-MOZZARELLA-CHEESE",60,2700),
    ("RM-BUTTER",         60, 1950),
    ("RM-YOGURT",        100,  930),
    ("RM-MILK",          150,  460),
    # Beverages (pre-packed)
    ("RM-COLA-CAN",      500,  310),
    ("RM-ORANGE-JUICE-CARTON",200, 620),
    ("RM-WATER-BOTTLE-500ML",1000, 115),
    ("RM-MANGO-JUICE-CARTON",200,  620),
    ("RM-SPARKLING-WATER-330ML",300, 230),
    # Spices
    ("RM-MIXED-SPICES",   30, 1550),
    ("RM-CUMIN",          20, 1150),
    ("RM-CORIANDER-POWDER",20,1150),
    ("RM-TURMERIC",       20,  930),
    ("RM-PAPRIKA",        20, 1390),
    ("RM-BLACK-PEPPER",   20, 1550),
    # Pantry
    ("RM-SUGAR",         150,  385),
    ("RM-COCOA-POWDER",   30, 1700),
    ("RM-VANILLA-EXTRACT", 10, 2330),
    ("RM-HONEY",          20, 1950),
    ("RM-DATES",          30, 1390),
]

try:
    se_name = make_material_receipt(STORES, RAW_MATERIAL_STOCK, OPENING_DATE)
    print(f"  ✓ Raw materials stocked in {STORES}: {se_name}")
except Exception as e:
    print(f"  ✗ Raw materials: {e}")
    frappe.db.rollback()
    frappe.db.begin()

# --- 2. Finished Goods in FG Warehouse ---
# 90 portions of each menu item as opening stock
FG_STOCK = []
menu_items = frappe.get_all(
    "Item",
    filters={"item_code": ["like", "FOOD-%"], "is_stock_item": 1},
    fields=["item_code", "valuation_rate"],
)
for item in menu_items:
    val_rate = item.valuation_rate or 200
    FG_STOCK.append((item.item_code, 90, val_rate))

try:
    se_name = make_material_receipt(FG, FG_STOCK, OPENING_DATE)
    print(f"  ✓ Finished goods stocked in {FG}: {se_name} ({len(FG_STOCK)} items)")
except Exception as e:
    print(f"  ✗ Finished goods: {e}")
    frappe.db.rollback()
    frappe.db.begin()

frappe.db.commit()

# Verify stock levels
print("\n  Stock verification (sample):")
from frappe.utils import flt
sample_items = ["RM-CHICKEN-BREAST", "RM-TOMATOES", "FOOD-MN-001", "FOOD-BV-004"]
for item_code in sample_items:
    qty = frappe.db.sql("""
        SELECT SUM(actual_qty) FROM `tabStock Ledger Entry`
        WHERE item_code = %s AND warehouse IN (%s, %s) AND is_cancelled = 0
    """, (item_code, STORES, FG))[0][0] or 0
    print(f"    {item_code}: {flt(qty, 1)} units")

print(f"\n✓ Step 7 complete: inventory populated.\n")
frappe.destroy()
