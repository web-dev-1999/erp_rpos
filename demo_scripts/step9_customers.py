"""Step 9: Customer Generation — 80 customers with walk-in + repeat patterns."""
import frappe
import random

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")

# Customer group
if not frappe.db.exists("Customer Group", "Restaurant Guests"):
    cg = frappe.new_doc("Customer Group")
    cg.customer_group_name = "Restaurant Guests"
    cg.parent_customer_group = "All Customer Groups"
    cg.insert(ignore_permissions=True)

# Territory
DEFAULT_TERRITORY = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"

FIRST_NAMES = [
    "Ahmed", "Mohammed", "Ali", "Omar", "Hassan", "Ibrahim", "Khalid", "Tariq",
    "Youssef", "Bilal", "Adel", "Samir", "Nabil", "Rami", "Faisal", "Ziad",
    "Aisha", "Fatima", "Nadia", "Sara", "Layla", "Mona", "Rania", "Hana",
    "Dina", "Lina", "Rana", "Dana", "Sana", "Huda", "Wafa", "Nour",
    "James", "David", "Michael", "Robert", "William", "Thomas", "Mark",
    "Jennifer", "Sarah", "Emily", "Jessica", "Amanda", "Lisa", "Megan",
    "Raj", "Vikram", "Priya", "Anita", "Deepak", "Sanjay",
]

LAST_NAMES = [
    "Al-Rashid", "Al-Hassan", "Ibrahim", "Mahmoud", "Abdullah", "Qasim",
    "Nasser", "Farouk", "Mansour", "Barakat", "Haddad", "Tawfiq",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller",
    "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Mehta",
    "Al-Farsi", "Al-Amin", "Khalil", "Saleh", "Saeed", "Yusuf",
]

print("\n=== STEP 9: CUSTOMER GENERATION ===\n")

created = 0

for i in range(1, 81):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    customer_name = f"{first} {last}"
    customer_code = f"CUST-{i:04d}"

    # Skip if already exists
    if frappe.db.exists("Customer", {"customer_name": customer_name}):
        continue

    try:
        cust = frappe.new_doc("Customer")
        cust.customer_name = customer_name
        cust.customer_type = "Individual"
        cust.customer_group = "Restaurant Guests"
        cust.territory = DEFAULT_TERRITORY
        cust.insert(ignore_permissions=True)
        created += 1

        if created % 10 == 0:
            print(f"  Created {created} customers...")

    except Exception as e:
        pass

frappe.db.commit()

total = frappe.db.count("Customer", {"customer_group": "Restaurant Guests"})
print(f"\n✓ Step 9 complete: {created} new customers created. Total restaurant guests: {total}\n")
frappe.destroy()
