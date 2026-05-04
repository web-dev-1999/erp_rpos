/**
 * Kitchen Display System page.
 *
 * Each station gets its own column of "tickets" (groups of items per order).
 * Items arrive via realtime events; kitchen staff click to advance status.
 *
 * Realtime rooms joined:
 *   rpos_station_<scrubbed_station_name>  — new kitchen tickets + status updates
 */

frappe.pages["kds"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Kitchen Display System",
        single_column: true,
    });

    new restaurant_pos.KDS(page, wrapper);
};

// ── Main KDS class ────────────────────────────────────────────────────────────

restaurant_pos = restaurant_pos || {};

restaurant_pos.KDS = class {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.$container = $(wrapper).find(".page-content");
        this.stations = {};   // stationName → { el, tickets }
        this.currentStation = null;

        this._setup_toolbar();
        this._load_stations();
    }

    // ── Toolbar ───────────────────────────────────────────────────────────────

    _setup_toolbar() {
        this.page.add_field({
            fieldtype: "Link",
            fieldname: "station_filter",
            label: "Station",
            options: "POS Kitchen Station",
            change: () => {
                const val = this.page.fields_dict.station_filter.get_value();
                this._filter_station(val);
            },
        });

        this.page.set_secondary_action("Refresh", () => this._refresh_all(), "refresh");
    }

    // ── Initialisation ────────────────────────────────────────────────────────

    async _load_stations() {
        const res = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "POS Kitchen Station",
                filters: { is_active: 1 },
                fields: ["name", "station_name", "station_type", "display_color"],
                order_by: "station_name asc",
            },
        });

        this.$container.html(this._build_layout(res.message || []));

        for (const station of res.message || []) {
            this.stations[station.name] = {
                el: this.$container.find(`.kds-station[data-station="${station.name}"]`),
                tickets: {},
            };
            this._subscribe_station(station.name);
            await this._load_queue(station.name);
        }
    }

    _build_layout(stations) {
        if (!stations.length) {
            return `<div class="kds-empty">No active kitchen stations configured.</div>`;
        }
        const cols = stations.map(s => `
            <div class="kds-station" data-station="${s.name}"
                 style="border-top: 4px solid ${s.display_color || "#3498db"}">
                <div class="kds-station-header">
                    <span class="kds-station-name">${s.station_name}</span>
                    <span class="kds-station-type">${s.station_type || ""}</span>
                    <span class="kds-station-count badge badge-light" data-count-for="${s.name}">0</span>
                </div>
                <div class="kds-tickets" data-tickets-for="${s.name}"></div>
            </div>`).join("");
        return `<div class="kds-grid">${cols}</div>`;
    }

    // ── Realtime subscription ─────────────────────────────────────────────────

    _subscribe_station(stationName) {
        const room = `rpos_station_${frappe.scrub(stationName)}`;
        frappe.socketio.socket.emit("join", room);

        frappe.realtime.on("rpos_kitchen_ticket", (data) => {
            if (data.station !== stationName) return;
            this._add_ticket(stationName, data);
        });

        frappe.realtime.on("rpos_item_status_update", (data) => {
            if (!this.stations[stationName]) return;
            this._update_item_chip(stationName, data);
        });
    }

    // ── Queue loading ─────────────────────────────────────────────────────────

    async _load_queue(stationName) {
        const res = await frappe.call({
            method: "restaurant_pos.api.kds.get_kitchen_queue",
            args: { station_name: stationName, limit: 50 },
        });

        const items = res.message || [];
        // Group by order
        const byOrder = {};
        items.forEach(item => {
            byOrder[item.order_name] = byOrder[item.order_name] || {
                order_name: item.order_name,
                table_id: item.table_id,
                items: [],
                sent_at: item.sent_at,
            };
            byOrder[item.order_name].items.push(item);
        });

        Object.values(byOrder).forEach(ticket => {
            this._add_ticket(stationName, {
                order: ticket.order_name,
                table: ticket.table_id,
                items: ticket.items,
                sent_at: ticket.sent_at,
                station: stationName,
            });
        });
    }

    async _refresh_all() {
        this.$container.find(".kds-tickets").empty();
        Object.values(this.stations).forEach(s => (s.tickets = {}));
        for (const name of Object.keys(this.stations)) {
            await this._load_queue(name);
        }
    }

    // ── Ticket rendering ──────────────────────────────────────────────────────

    _add_ticket(stationName, data) {
        const station = this.stations[stationName];
        if (!station) return;

        const orderName = data.order;
        let $ticket = station.el.find(`.kds-ticket[data-order="${orderName}"]`);

        if (!$ticket.length) {
            $ticket = $(this._ticket_html(data));
            station.el.find(".kds-tickets").append($ticket);
            station.tickets[orderName] = { items: {} };
            this._bind_ticket($ticket, stationName);
        }

        // Add / update items within ticket
        (data.items || []).forEach(item => {
            this._upsert_item_chip($ticket, item, stationName);
        });

        this._update_station_count(stationName);
        this._maybe_remove_ticket($ticket, stationName, orderName);
    }

    _ticket_html(data) {
        const elapsed = data.sent_at
            ? `<span class="kds-elapsed" data-sent="${data.sent_at}"></span>`
            : "";
        return `
            <div class="kds-ticket" data-order="${data.order}">
                <div class="kds-ticket-header">
                    <strong>Table ${data.table || "—"}</strong>
                    <small>${data.order}</small>
                    ${elapsed}
                </div>
                <div class="kds-items"></div>
            </div>`;
    }

    _upsert_item_chip($ticket, item, stationName) {
        const itemIdx = item.item_idx !== undefined ? item.item_idx : item.idx;
        let $chip = $ticket.find(`.kds-item[data-idx="${itemIdx}"]`);

        const statusClass = {
            sent: "status-sent",
            cooking: "status-cooking",
            ready: "status-ready",
        }[item.item_status] || "status-sent";

        const modifiers = item.modifiers
            ? _parse_modifiers(item.modifiers).map(m => `<li>${m.modifier_name}</li>`).join("")
            : "";

        const html = `
            <div class="kds-item ${statusClass}" data-idx="${itemIdx}"
                 data-order="${item.order_name || $ticket.data("order")}"
                 data-station="${stationName}">
                <span class="kds-item-qty">${item.qty}×</span>
                <span class="kds-item-name">${item.item_name}</span>
                ${item.seat_id ? `<span class="kds-seat">Seat ${item.seat_id}</span>` : ""}
                ${modifiers ? `<ul class="kds-modifiers">${modifiers}</ul>` : ""}
                ${item.notes ? `<div class="kds-item-notes">${item.notes}</div>` : ""}
                <button class="kds-advance-btn">▶</button>
            </div>`;

        if ($chip.length) {
            $chip.replaceWith(html);
        } else {
            $ticket.find(".kds-items").append(html);
        }
    }

    _bind_ticket($ticket, stationName) {
        $ticket.on("click", ".kds-advance-btn", async (e) => {
            const $item = $(e.currentTarget).closest(".kds-item");
            const orderName = $item.data("order");
            const itemIdx = $item.data("idx");

            const currentStatus = $item.hasClass("status-sent") ? "sent" : "cooking";
            const nextStatus = currentStatus === "sent" ? "cooking" : "ready";

            try {
                await frappe.call({
                    method: "restaurant_pos.api.kds.update_item_status",
                    args: { order_name: orderName, item_idx: itemIdx, new_status: nextStatus },
                });
                $item.removeClass("status-sent status-cooking status-ready")
                    .addClass(`status-${nextStatus}`);
                if (nextStatus === "ready") {
                    $item.find(".kds-advance-btn").remove();
                }
                this._maybe_remove_ticket($ticket, stationName, orderName);
            } catch (err) {
                frappe.show_alert({ message: err.message, indicator: "red" });
            }
        });
    }

    _update_item_chip(stationName, data) {
        const station = this.stations[stationName];
        if (!station) return;
        const $ticket = station.el.find(`.kds-ticket[data-order="${data.order}"]`);
        if (!$ticket.length) return;

        const $chip = $ticket.find(`.kds-item[data-idx="${data.item_idx}"]`);
        $chip.removeClass("status-sent status-cooking status-ready")
            .addClass(`status-${data.new_status}`);
        if (data.new_status === "ready") {
            $chip.find(".kds-advance-btn").remove();
        }

        this._maybe_remove_ticket($ticket, stationName, data.order);
    }

    _maybe_remove_ticket($ticket, stationName, orderName) {
        const allDone = $ticket.find(".kds-item").toArray().every(el => {
            return $(el).hasClass("status-ready") || $(el).hasClass("status-served");
        });
        if (allDone && $ticket.find(".kds-item").length > 0) {
            $ticket.addClass("kds-ticket-complete");
            setTimeout(() => $ticket.fadeOut(400, () => $ticket.remove()), 3000);
        }
        this._update_station_count(stationName);
    }

    _update_station_count(stationName) {
        const count = this.stations[stationName]?.el.find(
            ".kds-item:not(.status-ready)"
        ).length || 0;
        $(`[data-count-for="${stationName}"]`).text(count);
    }

    _filter_station(stationName) {
        if (!stationName) {
            this.$container.find(".kds-station").show();
        } else {
            this.$container.find(".kds-station").hide();
            this.$container.find(`.kds-station[data-station="${stationName}"]`).show();
        }
    }
};

// ── Elapsed time ticker ───────────────────────────────────────────────────────

setInterval(() => {
    $(".kds-elapsed[data-sent]").each(function () {
        const sent = new Date($(this).data("sent"));
        const mins = Math.floor((Date.now() - sent) / 60000);
        $(this).text(`${mins}m`);
        $(this).toggleClass("kds-overdue", mins >= 15);
    });
}, 30000);

// ── Helpers ───────────────────────────────────────────────────────────────────

function _parse_modifiers(json_str) {
    try { return JSON.parse(json_str) || []; }
    catch (_) { return []; }
}
