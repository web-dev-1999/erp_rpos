"""
Step 10: 90-day Sales Simulation — POS Invoices with realistic patterns.
Run with optional args: START_DAY END_DAY (default: 0 89)
"""
import frappe
import datetime
import random
import sys

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
CURRENCY = frappe.db.get_value("Company", COMPANY, "default_currency")

# Args for batching
START_DAY = int(sys.argv[1]) if len(sys.argv) > 1 else 0
END_DAY   = int(sys.argv[2]) if len(sys.argv) > 2 else 89

BASE_DATE = datetime.date.today() - datetime.timedelta(days=90)

# Load static data
POS_PROFILE = "Bar Terminal"  # existing POS profile with Finished Goods warehouse
print(f"  Using POS Profile: {POS_PROFILE}")

WAREHOUSE = frappe.db.get_value("POS Profile", POS_PROFILE, "warehouse") or "Finished Goods - AD"
INCOME_ACCOUNT = frappe.db.get_value(
    "Account", {"account_name": "Sales", "company": COMPANY, "is_group": 0}, "name"
) or frappe.db.get_value(
    "Account", {"root_type": "Income", "company": COMPANY, "is_group": 0}, "name"
)
COST_CENTER = frappe.db.get_value(
    "Cost Center", {"company": COMPANY, "is_group": 0}, "name"
)
DEBTORS = frappe.db.get_value(
    "Account", {"account_type": "Receivable", "company": COMPANY, "is_group": 0}, "name"
)

# Load menu items
MENU_ITEMS = frappe.get_all(
    "Item",
    filters={"item_code": ["like", "FOOD-%"], "is_stock_item": 1, "disabled": 0},
    fields=["item_code", "item_name", "item_group"],
)

STARTERS  = [i for i in MENU_ITEMS if i.item_group == "Starters"]
MAINS     = [i for i in MENU_ITEMS if i.item_group == "Mains"]
BEVERAGES = [i for i in MENU_ITEMS if i.item_group == "Beverages"]
DESSERTS  = [i for i in MENU_ITEMS if i.item_group == "Desserts"]

# Item prices
PRICES = {}
for ip in frappe.get_all("Item Price", filters={"price_list": "Standard Selling", "selling": 1},
                          fields=["item_code", "price_list_rate"]):
    PRICES[ip.item_code] = ip.price_list_rate

# Load customers
CUSTOMERS = frappe.get_all(
    "Customer",
    filters={"customer_group": "Restaurant Guests"},
    fields=["name", "customer_name"],
    limit=100,
)
CUSTOMER_NAMES = [c.name for c in CUSTOMERS]
WALKIN = frappe.db.get_value("Customer", {"customer_name": ["like", "Walk%"]}, "name")

# Payment methods
PAYMENT_MODES = [
    ("Cash",          0.45),
    ("Credit Card",   0.35),
    ("Debit Card",    0.12),
    ("Online",        0.08),
]


def weighted_choice(items_with_weights):
    names = [x[0] for x in items_with_weights]
    weights = [x[1] for x in items_with_weights]
    return random.choices(names, weights=weights, k=1)[0]


def orders_for_day(day_offset):
    """Return number of orders for given day."""
    date = BASE_DATE + datetime.timedelta(days=day_offset)
    weekday = date.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 4  # Fri, Sat, Sun
    base = random.randint(30, 45) if is_weekend else random.randint(18, 32)
    return base


def build_order_items():
    """Build a realistic set of items for one table order."""
    items = []
    covers = random.randint(1, 4)

    # Each cover gets a main
    mains_chosen = random.choices(MAINS, k=covers)
    for m in mains_chosen:
        items.append((m.item_code, 1))

    # ~70% chance of starter per cover
    for _ in range(covers):
        if random.random() < 0.70 and STARTERS:
            s = random.choice(STARTERS)
            items.append((s.item_code, 1))

    # ~90% chance of at least one drink per cover
    for _ in range(covers):
        if random.random() < 0.90 and BEVERAGES:
            b = random.choice(BEVERAGES)
            items.append((b.item_code, 1))

    # ~50% chance of dessert per cover
    for _ in range(covers):
        if random.random() < 0.50 and DESSERTS:
            d = random.choice(DESSERTS)
            items.append((d.item_code, 1))

    # Consolidate duplicates
    consolidated = {}
    for code, qty in items:
        consolidated[code] = consolidated.get(code, 0) + qty

    return [(code, qty) for code, qty in consolidated.items()], covers


def order_time(day_offset):
    """Return a posting datetime string with realistic meal time distribution."""
    date = BASE_DATE + datetime.timedelta(days=day_offset)
    roll = random.random()
    if roll < 0.12:       # Breakfast 8-10am
        hour = random.randint(8, 9)
        minute = random.randint(0, 59)
    elif roll < 0.45:     # Lunch 12-3pm
        hour = random.randint(12, 14)
        minute = random.randint(0, 59)
    elif roll < 0.58:     # Afternoon tea 3-6pm
        hour = random.randint(15, 17)
        minute = random.randint(0, 59)
    else:                 # Dinner 7-11pm
        hour = random.randint(19, 22)
        minute = random.randint(0, 59)
    return f"{date} {hour:02d}:{minute:02d}:00"


print(f"\n=== STEP 10: SALES SIMULATION (days {START_DAY}-{END_DAY}) ===\n")

invoice_count = 0
total_revenue = 0

for day in range(START_DAY, END_DAY + 1):
    day_date = BASE_DATE + datetime.timedelta(days=day)
    n_orders = orders_for_day(day)

    for order_num in range(n_orders):
        try:
            items_list, covers = build_order_items()
            if not items_list:
                continue

            # Choose customer
            if random.random() < 0.35 and CUSTOMER_NAMES:
                customer = random.choice(CUSTOMER_NAMES)
            else:
                customer = WALKIN or (CUSTOMER_NAMES[0] if CUSTOMER_NAMES else None)
            if not customer:
                continue

            posting_dt = order_time(day)
            posting_date = str(day_date)

            # Payment method
            pay_mode = weighted_choice(PAYMENT_MODES)

            # Build Sales Invoice (avoids POS Opening Entry requirement)
            inv = frappe.new_doc("Sales Invoice")
            inv.company = COMPANY
            inv.customer = customer
            inv.currency = CURRENCY
            inv.selling_price_list = "Standard Selling"
            inv.set_posting_time = 1
            inv.posting_date = posting_date
            inv.posting_time = posting_dt.split(" ")[1]
            inv.due_date = posting_date
            inv.debit_to = DEBTORS
            inv.cost_center = COST_CENTER
            inv.remarks = f"Restaurant sale — {pay_mode}"

            order_total = 0
            for item_code, qty in items_list:
                rate = PRICES.get(item_code, 500)
                inv.append("items", {
                    "item_code": item_code,
                    "qty": qty,
                    "rate": rate,
                    "amount": rate * qty,
                    "income_account": INCOME_ACCOUNT,
                    "cost_center": COST_CENTER,
                    "warehouse": WAREHOUSE,
                })
                order_total += rate * qty

            inv.insert(ignore_permissions=True)
            inv.submit()

            invoice_count += 1
            total_revenue += order_total

        except Exception as e:
            if invoice_count == 0:
                import traceback
                print(f"  FIRST ERROR (day {day}, order {order_num}): {traceback.format_exc()[:500]}")
            frappe.db.rollback()
            frappe.db.begin()

    if (day + 1) % 10 == 0 or day == END_DAY:
        frappe.db.commit()
        avg = total_revenue / max(invoice_count, 1)
        print(f"  Day {day+1:3d} | Invoices so far: {invoice_count:5d} | Revenue: PKR {total_revenue:,.0f} | Avg: PKR {avg:,.0f}")

frappe.db.commit()
print(f"\n✓ Step 10 complete: {invoice_count} POS invoices, PKR {total_revenue:,.0f} revenue.\n")
frappe.destroy()
