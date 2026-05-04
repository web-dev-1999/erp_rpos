"""Step 12: Shift Management — simplified using Expense Claim as shift log proxy,
or just a custom note on Employee. Since HRMS is not installed, we'll log
shift assignments as a data summary and link employees to cost centers."""
import frappe
from frappe.utils import today, add_days

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")

print("\n=== STEP 12: SHIFT MANAGEMENT (simplified) ===\n")
print("  Note: HRMS app not installed. Recording shift metadata via Employee custom notes.\n")

SHIFT_PLAN = {
    "Morning Shift (07:00-15:00)": [
        "manager@demo.pos", "supervisor1@demo.pos", "waiter1@demo.pos",
        "waiter2@demo.pos", "waiter7@demo.pos", "cashier1@demo.pos",
        "kitchen1@demo.pos", "kitchen3@demo.pos",
    ],
    "Afternoon Shift (14:00-22:00)": [
        "supervisor2@demo.pos", "waiter3@demo.pos", "waiter4@demo.pos",
        "cashier2@demo.pos", "kitchen2@demo.pos", "kitchen5@demo.pos",
    ],
    "Evening Shift (17:00-01:00)": [
        "supervisor3@demo.pos", "waiter5@demo.pos", "waiter6@demo.pos",
        "kitchen4@demo.pos",
    ],
}

updated = 0
for shift_name, users in SHIFT_PLAN.items():
    for user_id in users:
        emp = frappe.db.get_value("Employee", {"user_id": user_id}, ["name", "employee_name"], as_dict=True)
        if emp:
            # Store shift info in bio field
            frappe.db.set_value("Employee", emp.name, "bio", f"Assigned to: {shift_name}")
            updated += 1
            print(f"  ✓ {emp.employee_name}: {shift_name}")

frappe.db.commit()
print(f"\n✓ Step 12 complete: {updated} staff shift assignments recorded.\n")
print("  (Full shift scheduling requires HRMS app — available as separate ERPNext module)")
frappe.destroy()
