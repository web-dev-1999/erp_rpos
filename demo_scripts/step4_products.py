"""Step 4: Product Creation — 45 menu items across 4 categories."""
import frappe

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
CURRENCY = frappe.db.get_value("Company", COMPANY, "default_currency")

# Get selling price list
PRICE_LIST = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name") or "Standard Selling"
print(f"  Price list: {PRICE_LIST}")

# Ensure menu item groups exist
GROUPS = {
    "Starters":   {"color": "#FF6B35", "parent": "All Item Groups"},
    "Mains":      {"color": "#2ECC71", "parent": "All Item Groups"},
    "Beverages":  {"color": "#3498DB", "parent": "All Item Groups"},
    "Desserts":   {"color": "#9B59B6", "parent": "All Item Groups"},
}

for grp_name, grp_info in GROUPS.items():
    if not frappe.db.exists("Item Group", grp_name):
        ig = frappe.new_doc("Item Group")
        ig.item_group_name = grp_name
        ig.parent_item_group = grp_info["parent"]
        ig.insert(ignore_permissions=True)
        print(f"  Created item group: {grp_name}")

# Menu items: (code, name, group, selling_price_pkr, cost_price_pkr)
MENU_ITEMS = [
    # --- STARTERS ---
    ("FOOD-ST-001", "Hummus with Pita Bread",         "Starters",  650,  180),
    ("FOOD-ST-002", "Crispy Calamari",                "Starters",  950,  320),
    ("FOOD-ST-003", "Chicken Tikka Skewers",          "Starters", 1100,  380),
    ("FOOD-ST-004", "Garden Salad",                   "Starters",  550,  130),
    ("FOOD-ST-005", "Caesar Salad",                   "Starters",  750,  210),
    ("FOOD-ST-006", "Fattoush Salad",                 "Starters",  650,  160),
    ("FOOD-ST-007", "Mushroom Soup",                  "Starters",  580,  145),
    ("FOOD-ST-008", "Chicken Corn Soup",              "Starters",  620,  160),
    ("FOOD-ST-009", "Bruschetta",                     "Starters",  700,  200),
    ("FOOD-ST-010", "Spring Rolls (Veg)",             "Starters",  580,  150),
    # --- MAINS ---
    ("FOOD-MN-001", "Grilled Chicken Breast",         "Mains",    1650,  480),
    ("FOOD-MN-002", "Beef Tenderloin Steak",          "Mains",    3200, 1050),
    ("FOOD-MN-003", "Lamb Chops",                     "Mains",    2800,  920),
    ("FOOD-MN-004", "Grilled Sea Bass",               "Mains",    2600,  880),
    ("FOOD-MN-005", "Shrimp Pasta",                   "Mains",    2200,  680),
    ("FOOD-MN-006", "Chicken Biryani",                "Mains",    1450,  390),
    ("FOOD-MN-007", "Beef Burger",                    "Mains",    1350,  420),
    ("FOOD-MN-008", "Club Sandwich",                  "Mains",    1100,  320),
    ("FOOD-MN-009", "Margherita Pizza",               "Mains",    1550,  430),
    ("FOOD-MN-010", "Chicken Alfredo Pasta",          "Mains",    1850,  520),
    ("FOOD-MN-011", "Vegetable Curry with Rice",      "Mains",    1200,  300),
    ("FOOD-MN-012", "Salmon Fillet with Vegetables",  "Mains",    2900,  980),
    ("FOOD-MN-013", "Mixed Grill Platter",            "Mains",    3500, 1100),
    ("FOOD-MN-014", "Grilled Chicken Wrap",           "Mains",    1250,  380),
    ("FOOD-MN-015", "Pasta Arrabiata",                "Mains",    1300,  350),
    # --- BEVERAGES ---
    ("FOOD-BV-001", "Fresh Orange Juice",             "Beverages",  550,  120),
    ("FOOD-BV-002", "Fresh Lemon Mint",               "Beverages",  480,   90),
    ("FOOD-BV-003", "Mango Lassi",                    "Beverages",  580,  130),
    ("FOOD-BV-004", "Cola",                           "Beverages",  280,   60),
    ("FOOD-BV-005", "Mineral Water",                  "Beverages",  180,   30),
    ("FOOD-BV-006", "Sparkling Water",                "Beverages",  280,   55),
    ("FOOD-BV-007", "Hot Tea",                        "Beverages",  380,   50),
    ("FOOD-BV-008", "Espresso",                       "Beverages",  320,   60),
    ("FOOD-BV-009", "Cappuccino",                     "Beverages",  480,  100),
    ("FOOD-BV-010", "Fresh Strawberry Juice",         "Beverages",  650,  160),
    ("FOOD-BV-011", "Hot Chocolate",                  "Beverages",  550,  130),
    ("FOOD-BV-012", "Lemonade",                       "Beverages",  380,   75),
    # --- DESSERTS ---
    ("FOOD-DS-001", "Chocolate Lava Cake",            "Desserts",   780,  210),
    ("FOOD-DS-002", "Kunafa",                         "Desserts",   680,  180),
    ("FOOD-DS-003", "Tiramisu",                       "Desserts",   750,  220),
    ("FOOD-DS-004", "Crème Brûlée",                   "Desserts",   720,  200),
    ("FOOD-DS-005", "Umm Ali",                        "Desserts",   650,  170),
    ("FOOD-DS-006", "Fruit Salad",                    "Desserts",   480,  110),
    ("FOOD-DS-007", "Baklava",                        "Desserts",   580,  150),
    ("FOOD-DS-008", "Ice Cream Scoop",                "Desserts",   380,   90),
]

print("\n=== STEP 4: PRODUCT CREATION ===\n")

created = 0
for item_code, item_name, group, sell_price, cost_price in MENU_ITEMS:
    if frappe.db.exists("Item", item_code):
        print(f"  Skip (exists): {item_code}")
        continue

    item = frappe.new_doc("Item")
    item.item_code = item_code
    item.item_name = item_name
    item.item_group = group
    item.stock_uom = "Nos"
    item.is_sales_item = 1
    item.is_purchase_item = 0
    item.is_stock_item = 1
    item.valuation_method = "FIFO"
    item.standard_rate = sell_price
    item.valuation_rate = cost_price
    item.description = item_name
    item.custom_is_pos_item = 1 if frappe.db.has_column("Item", "custom_is_pos_item") else None
    item.insert(ignore_permissions=True)

    # Set selling price in price list
    if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": PRICE_LIST, "selling": 1}):
        ip = frappe.new_doc("Item Price")
        ip.item_code = item_code
        ip.price_list = PRICE_LIST
        ip.selling = 1
        ip.currency = CURRENCY
        ip.price_list_rate = sell_price
        ip.insert(ignore_permissions=True)

    created += 1
    print(f"  ✓ {item_code}: {item_name} ({group}) — PKR {sell_price:,}")

frappe.db.commit()
print(f"\n✓ Step 4 complete: {created} menu items created.\n")
frappe.destroy()
