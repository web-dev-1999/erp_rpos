"""Step 5: Combo/Bundled Products — 8 combo meals via ERPNext Product Bundle."""
import frappe

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
CURRENCY = frappe.db.get_value("Company", COMPANY, "default_currency")
PRICE_LIST = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name") or "Standard Selling"

COMBOS = [
    {
        "code": "COMBO-001",
        "name": "Family Grill Combo",
        "group": "Mains",
        "price": 6800,
        "items": [
            ("FOOD-MN-013", 1),  # Mixed Grill Platter
            ("FOOD-BV-001", 2),  # Fresh Orange Juice x2
            ("FOOD-DS-001", 1),  # Chocolate Lava Cake
        ],
    },
    {
        "code": "COMBO-002",
        "name": "Business Lunch Set",
        "group": "Mains",
        "price": 2200,
        "items": [
            ("FOOD-MN-008", 1),  # Club Sandwich
            ("FOOD-BV-007", 1),  # Hot Tea
            ("FOOD-DS-008", 1),  # Ice Cream Scoop
        ],
    },
    {
        "code": "COMBO-003",
        "name": "Seafood Lovers Deal",
        "group": "Mains",
        "price": 5800,
        "items": [
            ("FOOD-ST-002", 1),  # Crispy Calamari
            ("FOOD-MN-004", 1),  # Grilled Sea Bass
            ("FOOD-BV-006", 2),  # Sparkling Water x2
        ],
    },
    {
        "code": "COMBO-004",
        "name": "Couple Dinner Package",
        "group": "Mains",
        "price": 7500,
        "items": [
            ("FOOD-ST-005", 1),  # Caesar Salad
            ("FOOD-MN-002", 1),  # Beef Tenderloin Steak
            ("FOOD-MN-011", 1),  # Vegetable Curry with Rice
            ("FOOD-BV-009", 2),  # Cappuccino x2
            ("FOOD-DS-002", 1),  # Kunafa
        ],
    },
    {
        "code": "COMBO-005",
        "name": "Kids Meal Combo",
        "group": "Mains",
        "price": 1800,
        "items": [
            ("FOOD-MN-007", 1),  # Beef Burger
            ("FOOD-BV-004", 1),  # Cola
            ("FOOD-DS-008", 1),  # Ice Cream Scoop
        ],
    },
    {
        "code": "COMBO-006",
        "name": "Breakfast Special",
        "group": "Starters",
        "price": 1400,
        "items": [
            ("FOOD-ST-009", 1),  # Bruschetta
            ("FOOD-BV-008", 1),  # Espresso
            ("FOOD-BV-005", 1),  # Mineral Water
        ],
    },
    {
        "code": "COMBO-007",
        "name": "Chicken Feast",
        "group": "Mains",
        "price": 4200,
        "items": [
            ("FOOD-ST-003", 1),  # Chicken Tikka Skewers
            ("FOOD-MN-001", 1),  # Grilled Chicken Breast
            ("FOOD-MN-006", 1),  # Chicken Biryani
            ("FOOD-BV-002", 2),  # Fresh Lemon Mint x2
        ],
    },
    {
        "code": "COMBO-008",
        "name": "Dessert Platter",
        "group": "Desserts",
        "price": 2200,
        "items": [
            ("FOOD-DS-001", 1),  # Chocolate Lava Cake
            ("FOOD-DS-002", 1),  # Kunafa
            ("FOOD-DS-007", 1),  # Baklava
            ("FOOD-BV-011", 2),  # Hot Chocolate x2
        ],
    },
]

print("\n=== STEP 5: COMBO PRODUCTS ===\n")

created = 0
for combo in COMBOS:
    code = combo["code"]

    # Create the parent item if not exists
    if not frappe.db.exists("Item", code):
        item = frappe.new_doc("Item")
        item.item_code = code
        item.item_name = combo["name"]
        item.item_group = combo["group"]
        item.stock_uom = "Nos"
        item.is_sales_item = 1
        item.is_purchase_item = 0
        item.is_stock_item = 0  # Product bundle items are not stocked at parent level
        item.description = combo["name"]
        item.insert(ignore_permissions=True)

        # Set price
        ip = frappe.new_doc("Item Price")
        ip.item_code = code
        ip.price_list = PRICE_LIST
        ip.selling = 1
        ip.currency = CURRENCY
        ip.price_list_rate = combo["price"]
        ip.insert(ignore_permissions=True)

    # Create Product Bundle
    if not frappe.db.exists("Product Bundle", code):
        pb = frappe.new_doc("Product Bundle")
        pb.new_item_code = code
        pb.description = combo["name"]
        for child_code, qty in combo["items"]:
            pb.append("items", {
                "item_code": child_code,
                "qty": qty,
                "uom": "Nos",
                "description": frappe.db.get_value("Item", child_code, "item_name") or child_code,
            })
        pb.insert(ignore_permissions=True)
        created += 1
        print(f"  ✓ {code}: {combo['name']} — PKR {combo['price']:,} ({len(combo['items'])} items)")
    else:
        print(f"  Skip (exists): {code}")

frappe.db.commit()
print(f"\n✓ Step 5 complete: {created} combo products created.\n")
frappe.destroy()
