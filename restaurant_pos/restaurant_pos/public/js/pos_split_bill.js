/**
 * Bill Splitting UI.
 *
 * Opens a split dialog on top of the POS.  The split operates entirely on
 * POS Orders (no Sales Invoice is created or modified here).
 *
 * Architecture:
 *  1. User clicks "Split Bill"
 *  2. start_split() is called → parent order → SPLIT_IN_PROGRESS
 *  3. User drags items to named buckets
 *  4. create_split_plan() materialises child orders
 *  5. Each bucket is settled independently via the normal payment flow
 */

"use strict";

window.RPOS = window.RPOS || {};

RPOS.splitBill = (() => {

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
            if (target && !document.querySelector(".rpos-split-btn")) {
                obs.disconnect();
                cb();
            }
        });
        obs.observe(document.body, { childList: true, subtree: true });
    }

    function _injectButton() {
        const container = document.querySelector(".page-actions");
        if (!container) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-default btn-sm rpos-split-btn";
        btn.innerHTML = "⚖ Split Bill";
        btn.onclick = openSplitDialog;
        container.append(btn);
    }

    async function openSplitDialog() {
        const order = RPOS.orderManager.getOrder();
        if (!order) {
            frappe.show_alert({ message: "No active order", indicator: "orange" });
            return;
        }
        if (!order.items || !order.items.length) {
            frappe.show_alert({ message: "Order has no items", indicator: "orange" });
            return;
        }

        // Transition to SPLIT_IN_PROGRESS and get current items
        frappe.show_alert({ message: "Preparing split…", indicator: "blue" });
        const res = await frappe.call({
            method: "restaurant_pos.api.split.start_split",
            args: { order_name: order.name, client_version: order.version },
        });

        new SplitDialog(res.message).show();
    }

    return { init, openSplitDialog };
})();

// ── SplitDialog ───────────────────────────────────────────────────────────────

class SplitDialog {
    constructor(splitState) {
        this.state = splitState;
        this.orderName = splitState.order;
        this.sourceItems = splitState.items.map(i => ({ ...i, _remaining: i.qty }));
        this.splits = [
            { id: 1, name: "Bill A", customer: null, items: [] },
            { id: 2, name: "Bill B", customer: null, items: [] },
        ];
        this._nextSplitId = 3;
        this._dragData = null;
    }

    show() {
        this.dialog = new frappe.ui.Dialog({
            title: "Split Bill",
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "split_root" }],
            primary_action_label: "Create Split Bills",
            primary_action: () => this._submit(),
            secondary_action_label: "Cancel Split",
            secondary_action: () => this._abortSplit(),
        });
        this.dialog.show();
        this._render();
    }

    // ── Rendering ─────────────────────────────────────────────────────────────

    _render() {
        const $w = this.dialog.fields_dict.split_root.$wrapper;
        $w.html(this._html());
        this._bindEvents($w);
        this._refreshTotals();
    }

    _html() {
        return `
        <div class="rpos-split-root">
            <!-- Type selector -->
            <div class="rpos-split-controls mb-3 d-flex gap-2 align-items-center">
                <select class="form-control form-control-sm w-auto rpos-split-type">
                    <option value="item">Split by Items</option>
                    <option value="seat">Split by Seat</option>
                    <option value="equal">Split Equally</option>
                </select>
                <button class="btn btn-xs btn-primary rpos-add-split">+ Add Bill</button>
            </div>

            <!-- Two-panel layout: unassigned ← → split buckets -->
            <div class="rpos-split-panels">

                <!-- Left: unassigned pool -->
                <div class="rpos-panel rpos-unassigned-panel">
                    <h6>Unassigned Items</h6>
                    <div class="rpos-drop-zone rpos-unassigned-pool" data-pool="unassigned">
                        ${this._renderPool()}
                    </div>
                </div>

                <!-- Right: split buckets -->
                <div class="rpos-panel rpos-buckets-panel">
                    <div class="rpos-buckets-row">
                        ${this.splits.map(s => this._renderBucket(s)).join("")}
                    </div>
                </div>

            </div>
        </div>`;
    }

    _renderPool() {
        return this.sourceItems
            .filter(i => i._remaining > 0.001)
            .map(i => this._itemChip(i, i._remaining, "unassigned", null))
            .join("") || `<div class="rpos-pool-empty text-muted">All items assigned</div>`;
    }

    _renderBucket(split) {
        const total = split.items.reduce((s, i) => s + i.qty * i.rate, 0);
        return `
            <div class="rpos-bucket" data-split-id="${split.id}">
                <div class="rpos-bucket-header">
                    <input class="form-control form-control-sm rpos-bill-name"
                           value="${_esc(split.name)}" data-split-id="${split.id}">
                    <span class="rpos-bucket-total" data-total-for="${split.id}">
                        ${frappe.format(total, { fieldtype: "Currency" })}
                    </span>
                    <button class="btn btn-xs btn-danger rpos-remove-split"
                            data-split-id="${split.id}">×</button>
                </div>
                <div class="rpos-drop-zone rpos-bucket-items"
                     data-pool="split" data-split-id="${split.id}">
                    ${split.items.map(i => this._itemChip(i, i.qty, "split", split.id)).join("")}
                </div>
            </div>`;
    }

    _itemChip(item, qty, pool, splitId) {
        const key = `${pool}-${item.idx}`;
        return `
            <div class="rpos-item-chip" draggable="true"
                 data-idx="${item.idx}" data-pool="${pool}"
                 data-split-id="${splitId || ""}" data-key="${key}">
                <span class="rpos-chip-name">${_esc(item.item_name)}</span>
                <input type="number" class="form-control form-control-sm rpos-chip-qty"
                       value="${qty}" min="0.5" step="0.5"
                       data-idx="${item.idx}" data-pool="${pool}" data-split-id="${splitId || ""}">
                <span class="rpos-chip-rate text-muted">
                    @${frappe.format(item.rate, { fieldtype: "Currency" })}
                </span>
            </div>`;
    }

    // ── Event binding ─────────────────────────────────────────────────────────

    _bindEvents($w) {
        // Drag start
        $w.on("dragstart", ".rpos-item-chip", (e) => {
            const $el = $(e.currentTarget);
            this._dragData = {
                idx: parseInt($el.data("idx")),
                pool: $el.data("pool"),
                splitId: parseInt($el.data("split-id")) || null,
                qty: parseFloat($el.find(".rpos-chip-qty").val()),
            };
            e.originalEvent.dataTransfer.effectAllowed = "move";
        });

        // Drop zone
        $w.on("dragover", ".rpos-drop-zone", (e) => {
            e.preventDefault();
            $(e.currentTarget).addClass("rpos-drag-over");
        });
        $w.on("dragleave", ".rpos-drop-zone", (e) => {
            $(e.currentTarget).removeClass("rpos-drag-over");
        });
        $w.on("drop", ".rpos-drop-zone", (e) => {
            e.preventDefault();
            $(e.currentTarget).removeClass("rpos-drag-over");
            if (!this._dragData) return;
            const targetPool = $(e.currentTarget).data("pool");
            const targetSplitId = parseInt($(e.currentTarget).data("split-id")) || null;
            this._moveItem(this._dragData, targetPool, targetSplitId);
            this._render();
        });

        // Qty change
        $w.on("change", ".rpos-chip-qty", (e) => {
            const $el = $(e.currentTarget);
            this._handleQtyChange(
                parseInt($el.data("idx")),
                $el.data("pool"),
                parseInt($el.data("split-id")) || null,
                parseFloat($el.val()) || 0
            );
        });

        // Add split
        $w.on("click", ".rpos-add-split", () => {
            this.splits.push({
                id: this._nextSplitId++,
                name: `Bill ${_letter(this.splits.length)}`,
                customer: null,
                items: [],
            });
            this._render();
        });

        // Remove split
        $w.on("click", ".rpos-remove-split", (e) => {
            const id = parseInt($(e.currentTarget).data("split-id"));
            this._removeSplit(id);
        });

        // Bill name change
        $w.on("change", ".rpos-bill-name", (e) => {
            const id = parseInt($(e.currentTarget).data("split-id"));
            const split = this.splits.find(s => s.id === id);
            if (split) split.name = $(e.currentTarget).val();
        });

        // Split type
        $w.on("change", ".rpos-split-type", (e) => {
            if (e.target.value === "equal") this._applyEqualSplit();
            if (e.target.value === "seat") this._applySeatSplit();
        });
    }

    // ── Item movement ─────────────────────────────────────────────────────────

    _moveItem(drag, targetPool, targetSplitId) {
        const src = this.sourceItems.find(i => i.idx === drag.idx);
        if (!src) return;

        // Remove qty from source pool
        if (drag.pool === "unassigned") {
            src._remaining = Math.max(0, src._remaining - drag.qty);
        } else {
            const srcSplit = this.splits.find(s => s.id === drag.splitId);
            if (srcSplit) {
                srcSplit.items = srcSplit.items.filter(i => i.idx !== drag.idx);
            }
        }

        // Add to target
        if (targetPool === "unassigned") {
            src._remaining += drag.qty;
        } else if (targetPool === "split") {
            const targetSplit = this.splits.find(s => s.id === targetSplitId);
            if (targetSplit) {
                const existing = targetSplit.items.find(i => i.idx === drag.idx);
                if (existing) existing.qty += drag.qty;
                else targetSplit.items.push({ ...src, qty: drag.qty });
            }
        }
    }

    _handleQtyChange(idx, pool, splitId, newQty) {
        const src = this.sourceItems.find(i => i.idx === idx);
        if (!src || !splitId) return;

        const split = this.splits.find(s => s.id === splitId);
        if (!split) return;

        const item = split.items.find(i => i.idx === idx);
        if (!item) return;

        const otherAllocated = this.splits
            .filter(s => s.id !== splitId)
            .reduce((sum, s) => {
                const fi = s.items.find(i => i.idx === idx);
                return sum + (fi ? fi.qty : 0);
            }, 0);

        const maxQty = src.qty - otherAllocated;
        if (newQty > maxQty) {
            frappe.show_alert({ message: `Max ${maxQty} available`, indicator: "orange" });
            newQty = maxQty;
        }

        const oldQty = item.qty;
        item.qty = newQty;
        src._remaining += (oldQty - newQty);
        this._refreshTotals();
    }

    _removeSplit(splitId) {
        const split = this.splits.find(s => s.id === splitId);
        if (split) {
            split.items.forEach(i => {
                const src = this.sourceItems.find(s => s.idx === i.idx);
                if (src) src._remaining += i.qty;
            });
        }
        this.splits = this.splits.filter(s => s.id !== splitId);
        this._render();
    }

    _applyEqualSplit() {
        this.sourceItems.forEach(i => (i._remaining = i.qty));
        this.splits.forEach(s => (s.items = []));
        const n = this.splits.length;

        this.sourceItems.forEach(item => {
            const perSplit = parseFloat((item.qty / n).toFixed(3));
            this.splits.forEach((split, i) => {
                const q = i === n - 1 ? item.qty - perSplit * (n - 1) : perSplit;
                split.items.push({ ...item, qty: q });
            });
            item._remaining = 0;
        });
        this._render();
    }

    _applySeatSplit() {
        this.sourceItems.forEach(i => (i._remaining = i.qty));
        this.splits = [];
        this._nextSplitId = 1;

        const seats = [...new Set(this.sourceItems.map(i => i.seat_id || "No Seat"))];
        seats.forEach(seat => {
            const split = { id: this._nextSplitId++, name: seat, customer: null, items: [] };
            this.sourceItems
                .filter(i => (i.seat_id || "No Seat") === seat)
                .forEach(i => {
                    split.items.push({ ...i, qty: i.qty });
                    i._remaining = 0;
                });
            this.splits.push(split);
        });
        this._render();
    }

    _refreshTotals() {
        this.splits.forEach(split => {
            const total = split.items.reduce((s, i) => s + i.qty * i.rate, 0);
            $(`[data-total-for="${split.id}"]`).text(
                frappe.format(total, { fieldtype: "Currency" })
            );
        });
    }

    // ── Submission ────────────────────────────────────────────────────────────

    async _submit() {
        const activeSplits = this.splits.filter(s => s.items.length > 0);
        if (!activeSplits.length) {
            frappe.msgprint("Assign at least one item to a bill");
            return;
        }

        const hasUnassigned = this.sourceItems.some(i => i._remaining > 0.001);
        if (hasUnassigned) {
            const go = await new Promise(resolve =>
                frappe.confirm(
                    "Some items are unassigned and will be placed on a Remainder bill. Continue?",
                    () => resolve(true), () => resolve(false)
                )
            );
            if (!go) return;
        }

        const splitConfig = {
            type: "item_split",
            splits: activeSplits.map(s => ({
                name: s.name,
                customer: s.customer,
                items: s.items.map(i => ({ item_idx: i.idx, qty: i.qty })),
            })),
        };

        frappe.show_alert({ message: "Creating split orders…", indicator: "blue" });

        try {
            const res = await frappe.call({
                method: "restaurant_pos.api.split.create_split_plan",
                args: {
                    order_name: this.orderName,
                    split_config: JSON.stringify(splitConfig),
                    client_version: this.state.version,
                },
            });

            this.dialog.hide();
            const { children } = res.message;

            frappe.show_alert({
                message: `${children.length} split bill(s) created`,
                indicator: "green",
            });

            RPOS.splitBill._openPaymentQueue(children);

        } catch (err) {
            frappe.msgprint({
                title: "Split Failed",
                message: err.message || "Unknown error",
                indicator: "red",
            });
        }
    }

    async _abortSplit() {
        const order = RPOS.orderManager.getOrder();
        await frappe.call({
            method: "restaurant_pos.api.split.abort_split",
            args: { order_name: this.orderName, client_version: this.state.version },
        });
        this.dialog.hide();
        frappe.show_alert({ message: "Split cancelled", indicator: "orange" });
    }
}

// ── Post-split payment queue ──────────────────────────────────────────────────

RPOS.splitBill._openPaymentQueue = function (childOrderNames) {
    new PaymentQueueDialog(childOrderNames).show();
};

class PaymentQueueDialog {
    constructor(orderNames) {
        this.orderNames = orderNames;
        this.statuses = {};
        orderNames.forEach(n => (this.statuses[n] = "pending"));
    }

    show() {
        this.dialog = new frappe.ui.Dialog({
            title: "Settle Split Bills",
            size: "large",
            fields: [{ fieldtype: "HTML", fieldname: "queue_content" }],
        });
        this.dialog.show();
        this.dialog.$wrapper.find(".modal-footer").hide();
        this._render();
    }

    _render() {
        const $w = this.dialog.fields_dict.queue_content.$wrapper;
        $w.html(this.orderNames.map(n => `
            <div class="rpos-pay-row" data-order="${n}">
                <strong>${n}</strong>
                <span class="rpos-pay-status badge ${this.statuses[n] === "paid" ? "badge-success" : "badge-secondary"}">
                    ${this.statuses[n]}
                </span>
                ${this.statuses[n] === "pending"
                    ? `<button class="btn btn-sm btn-primary rpos-pay-btn" data-order="${n}">Pay</button>`
                    : ""}
            </div>
        `).join(""));

        $w.on("click", ".rpos-pay-btn", (e) => {
            const orderName = $(e.currentTarget).data("order");
            this._paySplit(orderName);
        });
    }

    async _paySplit(orderName) {
        await RPOS.orderManager.loadOrder(orderName);
        const preview = await RPOS.orderManager.getSettlementPreview();

        // Re-use the standard payment dialog pattern
        const payments = [{ mode_of_payment: "Cash", amount: preview.grand_total }];
        const res = await RPOS.orderManager.settleOrder(payments);

        if (res) {
            this.statuses[orderName] = "paid";
            this._render();

            const allPaid = Object.values(this.statuses).every(s => s === "paid");
            if (allPaid) {
                frappe.show_alert({ message: "All split bills settled!", indicator: "green" });
                setTimeout(() => this.dialog.hide(), 1500);
            }
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(str) {
    return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function _letter(n) {
    return String.fromCharCode(65 + n);
}

// Boot
$(document).on("frappe_ready app_ready page-change", () => RPOS.splitBill.init());
