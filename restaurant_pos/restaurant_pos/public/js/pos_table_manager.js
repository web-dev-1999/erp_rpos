/**
 * Table / Floor Plan manager.
 *
 * Adds a "Tables" view to the POS that shows the floor plan with live status.
 * Clicking a table opens its current order or creates a new one.
 *
 * Only activates when window.location.pathname includes "/point-of-sale"
 * to avoid polluting non-POS pages.
 */

"use strict";

window.RPOS = window.RPOS || {};

RPOS.tableManager = (() => {
    let _dialog = null;
    let _tables = [];

    function init() {
        if (!_isPOSPage()) return;
        _waitForPOS(() => _injectButton());
    }

    function _isPOSPage() {
        return window.location.pathname.includes("point-of-sale") ||
               window.location.hash.includes("point-of-sale");
    }

    function _waitForPOS(cb) {
        const obs = new MutationObserver(() => {
            const target = document.querySelector(".pos-billing-section, .page-actions");
            if (target) { obs.disconnect(); cb(); }
        });
        obs.observe(document.body, { childList: true, subtree: true });
    }

    function _injectButton() {
        const container = document.querySelector(".page-actions");
        if (!container || document.querySelector(".rpos-tables-btn")) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-default btn-sm rpos-tables-btn";
        btn.innerHTML = "🪑 Tables";
        btn.onclick = openFloorPlan;
        container.prepend(btn);

        // Subscribe to live table updates
        RPOS.realtime.on("rpos_floor_plan_update", (data) => {
            _updateTableBadge(data.table, data.status);
        });
    }

    async function openFloorPlan() {
        _dialog = new frappe.ui.Dialog({
            title: "Floor Plan",
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "floor_content" }],
        });

        _dialog.show();
        _dialog.$wrapper.find(".modal-footer").hide();
        _dialog.fields_dict.floor_content.$wrapper.html(
            '<div class="rpos-floor-loading">Loading tables…</div>'
        );

        await _loadAndRender();
    }

    async function _loadAndRender() {
        const res = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "POS Table",
                filters: { is_active: 1 },
                fields: ["name", "table_number", "section_label", "capacity", "status", "current_order"],
                order_by: "table_number asc",
                limit: 200,
            },
        });
        _tables = res.message || [];
        _renderFloorPlan(_tables);
    }

    function _renderFloorPlan(tables) {
        if (!_dialog) return;

        const sections = {};
        tables.forEach(t => {
            const sec = t.section_label || "Main";
            sections[sec] = sections[sec] || [];
            sections[sec].push(t);
        });

        let html = '<div class="rpos-floor-grid">';
        for (const [section, tbls] of Object.entries(sections)) {
            html += `<div class="rpos-floor-section">
                <h6 class="rpos-section-label">${section}</h6>
                <div class="rpos-tables-row">`;
            tbls.forEach(t => {
                const cls = _statusClass(t.status);
                html += `
                    <div class="rpos-table-tile ${cls}" data-table="${t.name}"
                         title="${t.table_number} — ${t.status}">
                        <div class="rpos-table-num">${t.table_number}</div>
                        <div class="rpos-table-cap">${t.capacity} pax</div>
                        <div class="rpos-table-status">${t.status}</div>
                        ${t.current_order
                            ? `<div class="rpos-table-order">${t.current_order}</div>`
                            : ""}
                    </div>`;
            });
            html += "</div></div>";
        }
        html += "</div>";

        const $wrap = _dialog.fields_dict.floor_content.$wrapper;
        $wrap.html(html);

        $wrap.on("click", ".rpos-table-tile", async (e) => {
            const tableName = $(e.currentTarget).data("table");
            await _onTableClick(tableName);
        });
    }

    async function _onTableClick(tableName) {
        const table = _tables.find(t => t.name === tableName);
        if (!table) return;

        if (table.status === "Occupied" && table.current_order) {
            // Load existing order into POS
            _dialog.hide();
            await RPOS.orderManager.loadOrder(table.current_order);
        } else if (table.status === "Available") {
            // Create new order for this table
            _dialog.hide();
            await RPOS.orderManager.newOrder(tableName);
        } else {
            frappe.show_alert({ message: `Table is ${table.status}`, indicator: "orange" });
        }
    }

    function _updateTableBadge(tableName, status) {
        if (!_dialog || !_dialog.$wrapper) return;
        const $tile = _dialog.$wrapper.find(`.rpos-table-tile[data-table="${tableName}"]`);
        if (!$tile.length) return;

        $tile.removeClass("rpos-table-available rpos-table-occupied rpos-table-reserved rpos-table-cleaning")
            .addClass(_statusClass(status));
        $tile.find(".rpos-table-status").text(status);
    }

    function _statusClass(status) {
        return "rpos-table-" + (status || "available").toLowerCase().replace(/\s+/g, "-");
    }

    // Boot on Frappe ready
    $(document).on("frappe_ready app_ready page-change", init);

    return { openFloorPlan };
})();
