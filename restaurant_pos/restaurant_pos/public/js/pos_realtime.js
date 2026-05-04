/**
 * Realtime subscription manager for the Restaurant POS.
 *
 * Responsibilities:
 *  - Subscribe to order-specific rooms when an order is opened
 *  - Dispatch inbound events to registered handlers
 *  - Manage offline detection and sync queue flushing on reconnect
 *
 * This file must be loaded first (listed first in hooks.py app_include_js).
 */

"use strict";

window.RPOS = window.RPOS || {};

RPOS.realtime = (() => {
    const _handlers = {};   // event_type → [callback, ...]
    let _currentOrder = null;
    let _isOnline = navigator.onLine;

    // ── Initialise once socket is available ──────────────────────────────────

    function init() {
        if (!window.frappe || !frappe.socketio) return;

        // Global channel — floor plan updates
        frappe.realtime.on("rpos_global", (data) => _dispatch("rpos_global", data));

        // Order-scoped channel — item updates, status changes
        frappe.realtime.on("rpos_order_event", (data) => _dispatch("rpos_order_event", data));

        // Item status updates from kitchen
        frappe.realtime.on("rpos_item_status_update", (data) =>
            _dispatch("rpos_item_status_update", data)
        );

        // Floor plan table status
        frappe.realtime.on("rpos_floor_plan_update", (data) =>
            _dispatch("rpos_floor_plan_update", data)
        );

        // Socket reconnect → flush offline queue
        if (frappe.socketio.socket) {
            frappe.socketio.socket.on("connect", () => {
                _isOnline = true;
                if (_currentOrder) subscribeToOrder(_currentOrder);
                RPOS.syncQueue.flush();
                _dispatch("rpos_reconnected", {});
            });
            frappe.socketio.socket.on("disconnect", () => {
                _isOnline = false;
                _dispatch("rpos_disconnected", {});
            });
        }
    }

    function subscribeToOrder(orderName) {
        _currentOrder = orderName;
        if (frappe.socketio?.socket) {
            frappe.socketio.socket.emit("doc_subscribe", "POS Order", orderName);
        }
    }

    function unsubscribeFromOrder(orderName) {
        if (frappe.socketio?.socket) {
            frappe.socketio.socket.emit("doc_unsubscribe", "POS Order", orderName);
        }
        if (_currentOrder === orderName) _currentOrder = null;
    }

    function on(eventType, handler) {
        _handlers[eventType] = _handlers[eventType] || [];
        _handlers[eventType].push(handler);
    }

    function off(eventType, handler) {
        if (!_handlers[eventType]) return;
        _handlers[eventType] = _handlers[eventType].filter(h => h !== handler);
    }

    function isOnline() { return _isOnline; }

    function _dispatch(eventType, data) {
        (_handlers[eventType] || []).forEach(h => {
            try { h(data); } catch (e) { console.error("[RPOS realtime]", e); }
        });
    }

    // Initialise when Frappe is ready
    $(document).on("frappe_ready app_ready", init);
    if (document.readyState !== "loading") setTimeout(init, 500);

    return { init, on, off, subscribeToOrder, unsubscribeFromOrder, isOnline };
})();


// ── Offline sync queue ────────────────────────────────────────────────────────
/**
 * Operations queued while offline are stored in localStorage and replayed
 * on reconnect.  Conflict resolution: server version wins.
 */
RPOS.syncQueue = (() => {
    const KEY = "rpos_sync_queue_v1";

    function enqueue(method, args) {
        const q = _load();
        q.push({ id: Date.now() + Math.random(), method, args, ts: new Date().toISOString() });
        _save(q);
    }

    async function flush() {
        const q = _load();
        if (!q.length) return;

        const failed = [];
        for (const op of q) {
            try {
                await frappe.call({ method: op.method, args: op.args });
            } catch (err) {
                // 409 / version conflict → server has moved on; silently discard
                if (err?.exc_type === "ValidationError" && err?.message?.includes("Version")) {
                    console.warn("[RPOS syncQueue] Conflict discarded:", op.method);
                } else {
                    failed.push(op);
                }
            }
        }
        _save(failed);
        if (q.length > failed.length) {
            frappe.show_alert({ message: `${q.length - failed.length} offline operation(s) synced`, indicator: "green" });
        }
    }

    function size() { return _load().length; }

    function _load() {
        try { return JSON.parse(localStorage.getItem(KEY) || "[]"); }
        catch (_) { return []; }
    }

    function _save(q) { localStorage.setItem(KEY, JSON.stringify(q)); }

    return { enqueue, flush, size };
})();
