"""Step 2: User & Staff Setup — manager, supervisors, waiters, cashiers, kitchen staff."""
import frappe
from frappe.utils import today, add_days

frappe.init(site="frontend")
frappe.connect()

COMPANY = frappe.defaults.get_global_default("company")
ABBR = frappe.db.get_value("Company", COMPANY, "abbr")


def get_or_create_dept(dept_name):
    full_name = f"{dept_name} - {ABBR}"
    if not frappe.db.exists("Department", full_name):
        d = frappe.new_doc("Department")
        d.department_name = dept_name
        d.company = COMPANY
        d.insert(ignore_permissions=True)
        print(f"  Created department: {full_name}")
    return full_name


STAFF = [
    # (first, last, username_key, frappe_roles, department_base, designation)
    ("Ahmad",   "Al-Rashid",  "manager",     ["POS Manager", "System Manager"],  "Management",  "Restaurant Manager"),
    ("Fatima",  "Hassan",     "supervisor1", ["POS Manager"],                    "Operations",  "Shift Supervisor"),
    ("Khalid",  "Al-Farsi",   "supervisor2", ["POS Manager"],                    "Operations",  "Shift Supervisor"),
    ("Nadia",   "Ibrahim",    "supervisor3", ["POS Manager"],                    "Operations",  "Shift Supervisor"),
    ("Omar",    "Yusuf",      "waiter1",     ["POS Cashier"],                    "Service",     "Waiter"),
    ("Layla",   "Mahmoud",    "waiter2",     ["POS Cashier"],                    "Service",     "Waitress"),
    ("Hassan",  "Al-Amin",    "waiter3",     ["POS Cashier"],                    "Service",     "Waiter"),
    ("Sara",    "Khalil",     "waiter4",     ["POS Cashier"],                    "Service",     "Waitress"),
    ("Tariq",   "Nasser",     "waiter5",     ["POS Cashier"],                    "Service",     "Waiter"),
    ("Rania",   "Farouk",     "waiter6",     ["POS Cashier"],                    "Service",     "Waitress"),
    ("Youssef", "Abdallah",   "waiter7",     ["POS Cashier"],                    "Service",     "Waiter"),
    ("Mona",    "Samir",      "cashier1",    ["POS Cashier", "Accounts User"],   "Accounts",    "Cashier"),
    ("Bilal",   "Qasim",      "cashier2",    ["POS Cashier", "Accounts User"],   "Accounts",    "Cashier"),
    ("Adel",    "Mansour",    "kitchen1",    ["Kitchen Staff"],                  "Production",  "Head Chef"),
    ("Hana",    "Tawfiq",     "kitchen2",    ["Kitchen Staff"],                  "Production",  "Sous Chef"),
    ("Jamal",   "Barakat",    "kitchen3",    ["Kitchen Staff"],                  "Production",  "Line Cook"),
    ("Dina",    "Saleh",      "kitchen4",    ["Kitchen Staff"],                  "Production",  "Line Cook"),
    ("Ramzi",   "Haddad",     "kitchen5",    ["Kitchen Staff"],                  "Production",  "Kitchen Assistant"),
]

MALE_NAMES = {"Ahmad","Khalid","Omar","Hassan","Tariq","Youssef","Bilal","Adel","Jamal","Ramzi"}

DEFAULT_PW = "Demo@123456"

print("\n=== STEP 2: USER & STAFF SETUP ===\n")

# Ensure Designations exist
for desig in ["Restaurant Manager", "Shift Supervisor", "Waiter", "Waitress", "Cashier",
              "Head Chef", "Sous Chef", "Line Cook", "Kitchen Assistant"]:
    if not frappe.db.exists("Designation", desig):
        d = frappe.new_doc("Designation")
        d.designation_name = desig
        d.insert(ignore_permissions=True)
        print(f"  Created designation: {desig}")

# Ensure custom roles exist
for role_name in ["POS Manager", "POS Cashier", "Kitchen Staff"]:
    if not frappe.db.exists("Role", role_name):
        r = frappe.new_doc("Role")
        r.role_name = role_name
        r.desk_access = 1
        r.insert(ignore_permissions=True)
        print(f"  Created role: {role_name}")

created_users = 0
created_employees = 0

for first, last, username_key, roles, dept_base, desig in STAFF:
    email = f"{username_key}@demo.pos"
    full_name = f"{first} {last}"
    dept = get_or_create_dept(dept_base)

    # Create or update User
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        existing_roles = [r.role for r in user.roles]
        changed = False
        for r in roles:
            if r not in existing_roles:
                user.append("roles", {"role": r})
                changed = True
        if changed:
            user.save(ignore_permissions=True)
    else:
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = first
        user.last_name = last
        user.full_name = full_name
        user.send_welcome_email = 0
        user.new_password = DEFAULT_PW
        user.user_type = "System User"
        for r in roles:
            user.append("roles", {"role": r})
        user.insert(ignore_permissions=True)
        created_users += 1

    print(f"  {'✓' if frappe.db.exists('User', email) else '✗'} {full_name} ({email})")

    # Create Employee if missing
    if not frappe.db.exists("Employee", {"user_id": email}):
        emp = frappe.new_doc("Employee")
        emp.first_name = first
        emp.last_name = last
        emp.employee_name = full_name
        emp.user_id = email
        emp.company = COMPANY
        emp.department = dept
        emp.designation = desig
        emp.date_of_joining = add_days(today(), -180)
        emp.date_of_birth = add_days(today(), -10950)  # ~30 years ago
        emp.status = "Active"
        emp.gender = "Male" if first in MALE_NAMES else "Female"
        emp.insert(ignore_permissions=True)
        created_employees += 1
        print(f"    → Employee: {emp.name}")

frappe.db.commit()
print(f"\n✓ Step 2 complete: {created_users} new users, {created_employees} new employee records.\n")
frappe.destroy()
