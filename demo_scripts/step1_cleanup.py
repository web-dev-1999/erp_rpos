"""Step 1: Cleanup — remove test/demo data, preserve core masters."""
import frappe

frappe.init(site="frontend")
frappe.connect()


def remove_pos_data():
    for dt in ["POS Reservation", "POS Order Item", "POS Order"]:
        count = frappe.db.count(dt)
        frappe.db.sql(f"DELETE FROM `tab{dt}`")
        print(f"  Deleted {count} records from {dt}")
    frappe.db.sql("UPDATE `tabPOS Table` SET status = 'Available', current_order = NULL")
    print("  Reset all POS Tables to Available")


def remove_docs(dt):
    names = frappe.db.sql(f"SELECT name FROM `tab{dt}`", pluck="name")
    deleted = 0
    for name in names:
        try:
            doc = frappe.get_doc(dt, name)
            if hasattr(doc, "docstatus") and doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
            deleted += 1
        except Exception:
            pass
    print(f"  {dt}: deleted {deleted}/{len(names)}")


def remove_demo_users():
    patterns = ["%@demo.pos"]
    deleted = 0
    for pattern in patterns:
        users = frappe.db.sql(
            "SELECT name FROM `tabUser` WHERE name LIKE %s", (pattern,), pluck="name"
        )
        for u in users:
            try:
                frappe.delete_doc("User", u, ignore_permissions=True, force=True)
                deleted += 1
            except Exception:
                pass
    print(f"  Demo users deleted: {deleted}")


print("\n=== STEP 1: CLEANUP ===\n")
remove_pos_data()
for dt in ["POS Invoice", "Sales Invoice", "Sales Order", "Delivery Note"]:
    remove_docs(dt)
for dt in ["Purchase Invoice", "Purchase Receipt", "Purchase Order"]:
    remove_docs(dt)
remove_docs("Payment Entry")
remove_docs("Stock Entry")
remove_demo_users()

# Remove previously seeded demo items/customers/suppliers
for dt, col, pattern in [
    ("Item", "item_code", "DEMO-%"),
    ("Item", "item_code", "FOOD-%"),
    ("Customer", "customer_name", "Demo %"),
    ("Supplier", "supplier_name", "Demo %"),
]:
    names = frappe.db.sql(
        f"SELECT name FROM `tab{dt}` WHERE `{col}` LIKE %s", (pattern,), pluck="name"
    )
    for name in names:
        try:
            frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
        except Exception:
            pass
    if names:
        print(f"  Removed {len(names)} {dt} matching {pattern}")

frappe.db.commit()
print("\n✓ Cleanup complete.\n")
frappe.destroy()
