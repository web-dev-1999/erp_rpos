"""
Item modifier API — returns modifier groups applicable to an item.
"""
import frappe


@frappe.whitelist()
def get_item_modifiers(item_code):
    """
    Return all modifier groups for an item, checking both item-specific
    and item-group-level mappings.
    """
    item_group = frappe.db.get_value("Item", item_code, "item_group")

    maps = frappe.db.sql(
        """
        SELECT modifier_group, sequence
        FROM `tabPOS Item Modifier Map`
        WHERE item_code = %(item_code)s
           OR item_group = %(item_group)s
        ORDER BY sequence ASC
        """,
        {"item_code": item_code, "item_group": item_group or ""},
        as_dict=True,
    )

    if not maps:
        return []

    seen = set()
    result = []
    for m in maps:
        gname = m["modifier_group"]
        if gname in seen:
            continue
        seen.add(gname)

        group = frappe.get_doc("POS Modifier Group", gname)
        result.append({
            "name": group.name,
            "group_name": group.group_name,
            "is_required": group.is_required,
            "min_selections": group.min_selections or 0,
            "max_selections": group.max_selections or 1,
            "options": [
                {
                    "name": o.name,
                    "option_name": o.option_name,
                    "price_adjustment": o.price_adjustment or 0,
                    "is_default": o.is_default,
                }
                for o in group.options
                if o.is_active
            ],
        })

    return result


@frappe.whitelist()
def apply_void(order_name, item_idx, manager_user, manager_password, reason):
    """
    Void a sent/cooking/ready item after manager authentication.
    Creates an audit record and removes the item from the order.
    """
    import frappe.auth

    # Authenticate the manager
    try:
        frappe.auth.LoginManager().authenticate(manager_user, manager_password)
    except Exception:
        frappe.throw(frappe._("Manager authentication failed"))

    if not frappe.db.get_value("Has Role", {"parent": manager_user, "role": "POS Manager"}):
        frappe.throw(frappe._("User {0} does not have POS Manager role").format(manager_user))

    from restaurant_pos.api._helpers import _lock_order
    _lock_order(order_name)
    order = frappe.get_doc("POS Order", order_name)

    item_idx = int(item_idx)
    item = next((i for i in order.items if i.idx == item_idx), None)
    if not item:
        frappe.throw(frappe._("Item not found"))

    voided_item = {
        "item_code": item.item_code,
        "item_name": item.item_name,
        "qty": item.qty,
        "rate": item.rate,
        "status_at_void": item.item_status,
    }

    order.items = [i for i in order.items if i.idx != item_idx]
    order.version = (order.version or 0) + 1
    order.notes = (order.notes or "") + f"\nVOID by {manager_user}: {item.item_name} x{item.qty} — {reason}"
    order.save(ignore_permissions=True)
    frappe.db.commit()

    from restaurant_pos.api._helpers import _publish_order_event
    _publish_order_event(order_name, "item_voided", {"item_idx": item_idx, "voided_by": manager_user})

    return {"voided": voided_item, "order": order_name}
