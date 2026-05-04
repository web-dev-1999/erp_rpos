/**
 * POS Order Manager.
 *
 * Central state manager for the active POS Order.  The POS UI reads/writes
 * through this object, not directly through frappe.call, so that:
 *  - Optimistic concurrency (version) is always enforced
 *  - Offline queueing is transparent
 *  - Realtime updates are reconciled with local state
 */

"use strict";

window.RPOS = window.RPOS || {};

RPOS.orderManager = (() => {
    let _order = null;          // Current in-memory POS Order dict
    let _listeners = [];        // onChange callbacks

    // ── Order lifecycle ───────────────────────────────────────────────────────

    async function newOrder(tableId, posProfile, customer, guestCount) {
        posProfile = posProfile || _getActivePOSProfile();
        if (!posProfile) {
            frappe.msgprint("No POS Profile found. Please configure one.");
            return null;
        }

        const res = await _call(
            "restaurant_pos.api.order.create_order",
            { pos_profile: posProfile, table_id: tableId, customer, guest_count: guestCount || 1 },
            true  // always online for create
        );
        _setOrder(res.message);
        RPOS.realtime.subscribeToOrder(_order.name);
        return _order;
    }

    async function loadOrder(orderName) {
        const res = await frappe.call({
            method: "restaurant_pos.api.order.get_order",
            args: { order_name: orderName },
        });
        _setOrder(res.message);
        RPOS.realtime.subscribeToOrder(_order.name);
        return _order;
    }

    function getOrder() { return _order; }

    function getVersion() { return _order ? _order.version : null; }

    // ── Item operations ───────────────────────────────────────────────────────

    async function addItem(itemCode, qty, rate, seatId, modifiers, notes) {
        _assertOrder();
        const args = {
            order_name: _order.name,
            item_code: itemCode,
            qty: qty || 1,
            rate,
            seat_id: seatId,
            modifiers: modifiers ? JSON.stringify(modifiers) : null,
            notes,
            client_version: _order.version,
        };
        const updated = await _callWithFallback(
            "restaurant_pos.api.order.add_item", args
        );
        _setOrder(updated);
        return _order;
    }

    async function updateItemQty(itemIdx, qty) {
        _assertOrder();
        const args = {
            order_name: _order.name,
            item_idx: itemIdx,
            qty,
            client_version: _order.version,
        };
        const updated = await _callWithFallback(
            "restaurant_pos.api.order.update_item_qty", args
        );
        _setOrder(updated);
        return _order;
    }

    async function removeItem(itemIdx) {
        return updateItemQty(itemIdx, 0);
    }

    // ── Kitchen ───────────────────────────────────────────────────────────────

    async function sendToKitchen(itemIdxs) {
        _assertOrder();
        const updated = await _call(
            "restaurant_pos.api.order.send_to_kitchen",
            {
                order_name: _order.name,
                item_idxs: itemIdxs ? JSON.stringify(itemIdxs) : null,
                client_version: _order.version,
            }
        );
        _setOrder(updated);
        return _order;
    }

    async function markItemServed(itemIdx) {
        _assertOrder();
        await _call("restaurant_pos.api.kds.mark_item_served", {
            order_name: _order.name,
            item_idx: itemIdx,
        });
        await _refresh();
        return _order;
    }

    // ── Settlement ────────────────────────────────────────────────────────────

    async function getSettlementPreview() {
        _assertOrder();
        const res = await frappe.call({
            method: "restaurant_pos.api.settlement.get_settlement_preview",
            args: { order_name: _order.name },
        });
        return res.message;
    }

    async function settleOrder(payments) {
        _assertOrder();
        const res = await _call(
            "restaurant_pos.api.settlement.settle_order",
            {
                order_name: _order.name,
                payments: JSON.stringify(payments),
                client_version: _order.version,
            }
        );
        if (res) {
            RPOS.realtime.unsubscribeFromOrder(_order.name);
            _setOrder(null);
        }
        return res;
    }

    async function cancelOrder(reason) {
        _assertOrder();
        const updated = await _call(
            "restaurant_pos.api.order.cancel_order",
            { order_name: _order.name, reason, client_version: _order.version }
        );
        RPOS.realtime.unsubscribeFromOrder(_order.name);
        _setOrder(null);
        return updated;
    }

    // ── Realtime reconciliation ───────────────────────────────────────────────

    RPOS.realtime.on("rpos_order_event", async (data) => {
        if (!_order || data.order !== _order.name) return;
        // Refresh from server — ensures version stays in sync
        await _refresh();
    });

    RPOS.realtime.on("rpos_item_status_update", (data) => {
        if (!_order || data.order !== _order.name) return;
        const item = (_order.items || []).find(i => i.idx === data.item_idx);
        if (item) {
            item.item_status = data.new_status;
            _notifyListeners();
        }
    });

    // ── Change listeners ──────────────────────────────────────────────────────

    function onChange(fn) {
        _listeners.push(fn);
        return () => { _listeners = _listeners.filter(l => l !== fn); };
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    function _setOrder(order) {
        _order = order;
        _notifyListeners();
    }

    function _notifyListeners() {
        _listeners.forEach(fn => { try { fn(_order); } catch (e) { console.error(e); } });
    }

    function _assertOrder() {
        if (!_order) frappe.throw("No active order");
    }

    async function _refresh() {
        if (!_order) return;
        const res = await frappe.call({
            method: "restaurant_pos.api.order.get_order",
            args: { order_name: _order.name },
        });
        _setOrder(res.message);
    }

    async function _call(method, args, forceOnline = false) {
        if (!forceOnline && !RPOS.realtime.isOnline()) {
            RPOS.syncQueue.enqueue(method, args);
            frappe.show_alert({ message: "Offline — operation queued", indicator: "orange" });
            return null;
        }
        const res = await frappe.call({ method, args });
        return res.message;
    }

    async function _callWithFallback(method, args) {
        try {
            return await _call(method, args);
        } catch (err) {
            if (err?.message?.includes("Version Conflict")) {
                // Server has a newer version — re-fetch and inform user
                await _refresh();
                frappe.show_alert({
                    message: "Order updated by another session. Your change was not applied — please retry.",
                    indicator: "orange",
                });
                return null;
            }
            throw err;
        }
    }

    function _getActivePOSProfile() {
        return (
            frappe.defaults.get_user_default("pos_profile") ||
            frappe.boot?.pos_profile ||
            null
        );
    }

    return {
        newOrder,
        loadOrder,
        getOrder,
        getVersion,
        addItem,
        updateItemQty,
        removeItem,
        sendToKitchen,
        markItemServed,
        getSettlementPreview,
        settleOrder,
        cancelOrder,
        onChange,
    };
})();
