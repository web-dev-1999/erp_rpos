from . import __version__ as app_version

app_name = "restaurant_pos"
app_title = "Restaurant POS"
app_publisher = "ILI Digital"
app_description = "Restaurant-grade POS system: orders, KDS, bill splitting"
app_email = "dev@ili.digital"
app_license = "MIT"
app_version = "1.0.0"

# ── Public assets injected on every page ────────────────────────────────────
# These are served from /assets/restaurant_pos/js/
# Only the POS page actually activates them (guarded inside each file).
app_include_js = [
    "/assets/restaurant_pos/js/pos_realtime.js",
    "/assets/restaurant_pos/js/pos_table_manager.js",
    "/assets/restaurant_pos/js/pos_order_manager.js",
    "/assets/restaurant_pos/js/pos_split_bill.js",
    "/assets/restaurant_pos/js/kds.js",
    "/assets/restaurant_pos/js/rpos_app.js",
]

app_include_css = [
    "/assets/restaurant_pos/css/restaurant_pos.css",
    "/assets/restaurant_pos/css/rpos.css",
]

# ── Document event hooks ─────────────────────────────────────────────────────
doc_events = {
    "POS Order": {
        "after_insert": "restaurant_pos.api.order.on_order_after_insert",
        "on_update":    "restaurant_pos.api.order.on_order_update",
        "on_cancel":    "restaurant_pos.api.order.on_order_cancel",
    },
    "POS Order Item": {
        "on_update": "restaurant_pos.api.kds.on_item_status_change",
    },
}

# ── Scheduled tasks ──────────────────────────────────────────────────────────
scheduler_events = {
    "hourly": [
        "restaurant_pos.api.order.cleanup_stale_orders",
    ],
    "cron": {
        "*/15 * * * *": [
            "restaurant_pos.api.reservation.check_reservation_auto_release",
        ],
    },
}

# ── Override JS (non-page JS for Frappe forms) ───────────────────────────────
# Not needed — we hook into POS page via app_include_js guard.

# ── Fixtures (export these with bench export-fixtures) ──────────────────────
fixtures = [
    {
        "doctype": "Custom Role",
        "filters": [["role_name", "in", ["POS Manager", "POS Cashier", "Kitchen Staff"]]],
    },
]
