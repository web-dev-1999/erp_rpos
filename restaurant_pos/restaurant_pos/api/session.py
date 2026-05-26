"""POS session management — wraps ERPNext POS Opening/Closing Entry."""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime, getdate, today, now_datetime as _now

# Sessions opened on the previous calendar day are treated as still valid
# until this hour (24-hour clock). A restaurant that opens at 10 AM and
# closes at 2 AM can set this to 6 — any check before 06:00 will consider
# a yesterday-opened session current rather than outdated.
_DAY_CUTOVER_HOUR = 6


def _is_session_outdated(period_start_date) -> bool:
    """
    A session is outdated when its start date is before *today's business date*.
    The business date rolls over at _DAY_CUTOVER_HOUR, so a session opened
    yesterday at 10 PM is still valid at 1 AM the following morning.
    """
    from datetime import datetime, timedelta
    now = _now()
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    business_date = now.date() if now.hour >= _DAY_CUTOVER_HOUR else (now - timedelta(days=1)).date()
    return getdate(period_start_date) < business_date


@frappe.whitelist()
def get_active_session(pos_profile):
    """
    Return the active POS Opening Entry for this profile, or None.
    Returns {"name": "...", "is_outdated": True/False} so the frontend
    can detect a session that must be renewed before new orders are taken.
    """
    result = frappe.db.get_value(
        "POS Opening Entry",
        {"pos_profile": pos_profile, "status": "Open", "docstatus": 1},
        ["name", "period_start_date"],
        as_dict=True,
        order_by="period_start_date desc",
    )
    if not result:
        return None
    return {"name": result.name, "is_outdated": _is_session_outdated(result.period_start_date)}


@frappe.whitelist()
def open_session(pos_profile, opening_cash=0):
    """Create and submit a POS Opening Entry. Returns the entry name."""
    profile = frappe.get_doc("POS Profile", pos_profile)

    entry = frappe.new_doc("POS Opening Entry")
    entry.pos_profile = pos_profile
    entry.company = profile.company
    entry.period_start_date = now_datetime()
    entry.user = frappe.session.user

    cash_added = False
    for pmt in (profile.payments or []):
        amount = flt(opening_cash) if pmt.mode_of_payment == "Cash" else 0
        entry.append("balance_details", {
            "mode_of_payment": pmt.mode_of_payment,
            "opening_amount": amount,
        })
        if pmt.mode_of_payment == "Cash":
            cash_added = True

    if not cash_added:
        entry.append("balance_details", {
            "mode_of_payment": "Cash",
            "opening_amount": flt(opening_cash),
        })

    entry.insert(ignore_permissions=True)
    entry.submit()
    frappe.db.commit()
    return entry.name


@frappe.whitelist()
def close_session(opening_entry, closing_cash=0):
    """
    Close the POS session.  Creates a POS Closing Entry if possible;
    always marks the Opening Entry as Closed regardless.
    """
    opening = frappe.get_doc("POS Opening Entry", opening_entry)

    invoices = _get_session_invoices(opening)

    closing_entry_name = None
    try:
        closing = frappe.new_doc("POS Closing Entry")
        closing.pos_opening_entry = opening_entry
        closing.pos_profile = opening.pos_profile
        closing.company = opening.company
        closing.period_start_date = opening.period_start_date
        closing.period_end_date = now_datetime()

        payment_totals = _get_payment_totals([i.name for i in invoices])
        for detail in opening.balance_details:
            expected = payment_totals.get(detail.mode_of_payment, 0)
            actual = flt(closing_cash) if detail.mode_of_payment == "Cash" else expected
            closing.append("payment_reconciliation", {
                "mode_of_payment": detail.mode_of_payment,
                "opening_amount": flt(detail.opening_amount),
                "expected_amount": expected,
                "closing_amount": actual,
                "difference": actual - expected,
            })

        closing.insert(ignore_permissions=True)
        closing.submit()
        closing_entry_name = closing.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "POS Closing Entry creation failed")

    frappe.db.set_value("POS Opening Entry", opening_entry, "status", "Closed")
    frappe.db.commit()

    return {
        "closing_entry": closing_entry_name,
        "invoice_count": len(invoices),
        "total_sales": sum(flt(i.grand_total) for i in invoices),
    }


@frappe.whitelist()
def get_session_summary(opening_entry):
    """Return stats shown in the Close Session dialog."""
    opening = frappe.get_doc("POS Opening Entry", opening_entry)

    invoices = _get_session_invoices(opening)
    total_sales = sum(flt(i.grand_total) for i in invoices)

    opening_cash = sum(
        flt(d.opening_amount) for d in opening.balance_details
        if d.mode_of_payment == "Cash"
    )

    cash_collected = 0
    if invoices:
        payment_totals = _get_payment_totals([i.name for i in invoices])
        cash_collected = payment_totals.get("Cash", 0)

    return {
        "invoice_count": len(invoices),
        "total_sales": total_sales,
        "expected_cash": opening_cash + cash_collected,
        "period_start": str(opening.period_start_date),
    }


def _get_session_invoices(opening):
    """
    Return submitted Sales Invoices (is_pos=1) for this session's profile
    posted on or after the session's start date.

    ERPNext 16 does not store pos_opening_entry on Sales Invoice, so we
    approximate by pos_profile + posting_date range.
    """
    start_date = getdate(opening.period_start_date)
    return frappe.get_all(
        "Sales Invoice",
        filters=[
            ["is_pos", "=", 1],
            ["pos_profile", "=", opening.pos_profile],
            ["docstatus", "=", 1],
            ["posting_date", ">=", start_date],
        ],
        fields=["name", "grand_total"],
    )


def _get_payment_totals(inv_names: list) -> dict:
    if not inv_names:
        return {}
    placeholders = ", ".join(["%s"] * len(inv_names))
    rows = frappe.db.sql(
        f"""SELECT mode_of_payment, COALESCE(SUM(amount), 0) as total
            FROM `tabSales Invoice Payment`
            WHERE parent IN ({placeholders})
            GROUP BY mode_of_payment""",
        inv_names,
        as_dict=True,
    )
    return {r.mode_of_payment: flt(r.total) for r in rows}
