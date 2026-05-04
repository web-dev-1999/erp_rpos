/**
 * Restaurant POS — full waiter-facing application.
 *
 * Views:  FloorView → OrderView → PaymentView
 * All views live inside a single full-screen container that replaces
 * the standard Frappe desk layout while the page is active.
 */

"use strict";
frappe.provide("rpos");

// Currency formatter — frappe.format() in v16 wraps values in a <div>; this
// extracts plain text so we never render raw HTML tags in the UI.
rpos._money = function (val) {
    const raw = frappe.format(val || 0, { fieldtype: "Currency" });
    if (typeof raw === "string" && raw.includes("<")) {
        return $("<span>").html(raw).text().trim();
    }
    return raw;
};

// ─────────────────────────────────────────────────────────────────────────────
//  App  (root controller)
// ─────────────────────────────────────────────────────────────────────────────

rpos.App = class {
    constructor(wrapper) {
        this.wrapper  = wrapper;
        this.posProfile = null;
        this.currentView = null;

        this._buildShell();
        this._loadPOSProfile().then(() => {
            this._setupRealtime();
            this.showFloor();
        });
    }

    onShow() {
        // Refresh floor whenever we navigate back to the page
        if (this.floorView) this.floorView.refresh();
    }

    // ── Shell ──────────────────────────────────────────────────────────────

    _buildShell() {
        $(this.wrapper).addClass("rpos-wrapper");

        // Force full-screen: hide Frappe sidebar & navbar chrome
        $(".layout-side-section").hide();
        $(".page-head").hide();
        $("body").addClass("rpos-fullscreen");

        this.$app = $(`
            <div class="rpos-app">
                <div class="rpos-header">
                    <div class="rpos-header-left">
                        <span class="rpos-logo">🍽 Restaurant POS</span>
                        <span class="rpos-breadcrumb"></span>
                    </div>
                    <div class="rpos-header-center">
                        <span class="rpos-clock"></span>
                    </div>
                    <div class="rpos-header-right">
                        <button class="rpos-btn rpos-btn-ghost rpos-btn-sm" id="rpos-reservation-btn">
                            📅 Reservations
                        </button>
                        <button class="rpos-btn rpos-btn-ghost rpos-btn-sm" id="rpos-floor-editor-btn">
                            ✏️ Edit Floor
                        </button>
                        <span class="rpos-user">${frappe.session.user_fullname || frappe.session.user}</span>
                    </div>
                </div>
                <div class="rpos-body"></div>
            </div>
        `).appendTo(this.wrapper);

        this.$body = this.$app.find(".rpos-body");
        this.$breadcrumb = this.$app.find(".rpos-breadcrumb");

        // Clock
        this._tickClock();
        setInterval(() => this._tickClock(), 1000);

        // Header buttons
        this.$app.find("#rpos-reservation-btn").on("click", () => new rpos.ReservationListDialog(this));
        this.$app.find("#rpos-floor-editor-btn").on("click", () => {
            if (this.floorView) this.floorView.toggleEditMode();
        });

        // Cleanup on page unload
        $(window).on("beforeunload.rpos", () => this._destroy());
    }

    _tickClock() {
        const now = new Date();
        this.$app.find(".rpos-clock").text(
            now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        );
    }

    _destroy() {
        $(".layout-side-section").show();
        $(".page-head").show();
        $("body").removeClass("rpos-fullscreen");
    }

    // ── POS Profile ────────────────────────────────────────────────────────

    async _loadPOSProfile() {
        const profiles = await frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: "POS Profile", filters: { disabled: 0 },
                    fields: ["name", "selling_price_list", "company",
                             "write_off_account", "write_off_cost_center",
                             "taxes_and_charges", "currency"],
                    limit: 20 },
        });
        const list = profiles.message || [];
        if (!list.length) {
            frappe.msgprint("No POS Profile configured. Please set one up first.");
            return;
        }
        // Use default or first
        const def = frappe.defaults.get_user_default("pos_profile");
        this.posProfile = list.find(p => p.name === def) || list[0];

        // Fetch payment methods
        const full = await frappe.call({
            method: "frappe.client.get",
            args: { doctype: "POS Profile", name: this.posProfile.name },
        });
        this.posProfile.payments = (full.message?.payments || []).map(p => p.mode_of_payment);
    }

    // ── Navigation ─────────────────────────────────────────────────────────

    showFloor() {
        this.$breadcrumb.text("");
        this.$app.find("#rpos-floor-editor-btn").show();
        if (!this.floorView) {
            this.floorView = new rpos.FloorView(this, this.$body);
        } else {
            this.floorView.show();
            this.floorView.refresh();
        }
        if (this.orderView) this.orderView.hide();
        if (this.paymentView) this.paymentView.hide();
        this.currentView = "floor";
    }

    showOrder(tableData) {
        this.$breadcrumb.html(
            `<span class="rpos-breadcrumb-link" id="rpos-back-floor">Floor</span>
             <span class="rpos-breadcrumb-sep">›</span>
             <span>Table ${tableData.table_number}</span>`
        );
        this.$breadcrumb.find("#rpos-back-floor").on("click", () => this.showFloor());
        this.$app.find("#rpos-floor-editor-btn").hide();

        if (this.floorView) this.floorView.hide();

        if (!this.orderView) {
            this.orderView = new rpos.OrderView(this, this.$body);
        }
        this.orderView.show();
        this.orderView.load(tableData);

        if (this.paymentView) this.paymentView.hide();
        this.currentView = "order";
    }

    showPayment(order) {
        if (!this.paymentView) {
            this.paymentView = new rpos.PaymentView(this, this.$body);
        }
        this.paymentView.show(order);
        if (this.orderView) this.orderView.hide();
        this.currentView = "payment";
    }

    backToOrder() {
        if (this.paymentView) this.paymentView.hide();
        if (this.orderView) this.orderView.show();
        this.currentView = "order";
    }

    // ── Realtime ───────────────────────────────────────────────────────────

    _setupRealtime() {
        // Join the floor plan room
        if (frappe.socketio?.socket) {
            frappe.socketio.socket.emit("join", "rpos_floor_plan");
        }

        frappe.realtime.on("rpos_floor_plan_update", (data) => {
            if (this.floorView) this.floorView.updateTable(data.table, data.status, data);
        });

        frappe.realtime.on("rpos_order_event", (data) => {
            if (this.orderView && this.orderView.order?.name === data.order) {
                this.orderView.refreshOrder();
            }
        });

        frappe.realtime.on("rpos_reservation_alert", (data) => {
            this._showReservationAlert(data);
        });
    }

    _showReservationAlert(data) {
        frappe.show_alert({
            message: `⏰ Table ${data.table}: ${data.guest} reservation overdue — please check`,
            indicator: "orange",
        }, 8);
        if (this.floorView) this.floorView.markTableAlert(data.table);
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Floor View
// ─────────────────────────────────────────────────────────────────────────────

rpos.FloorView = class {
    constructor(app, $parent) {
        this.app = app;
        this.$el = $(`<div class="rpos-floor-view"></div>`).appendTo($parent);
        this.floors = [];
        this.activeFloor = null;
        this.editMode = false;
        this.dragState = null;
        this._build();
        this.refresh();
    }

    show() { this.$el.show(); }
    hide() { this.$el.hide(); }

    _build() {
        this.$el.html(`
            <div class="rpos-floor-toolbar">
                <div class="rpos-floor-tabs"></div>
                <div class="rpos-floor-stats">
                    <span class="rpos-stat available">🟢 <b class="cnt-available">0</b> Available</span>
                    <span class="rpos-stat occupied">🟠 <b class="cnt-occupied">0</b> Occupied</span>
                    <span class="rpos-stat reserved">🔵 <b class="cnt-reserved">0</b> Reserved</span>
                    <span class="rpos-stat cleaning">🟡 <b class="cnt-cleaning">0</b> Cleaning</span>
                </div>
            </div>
            <div class="rpos-canvas-wrap">
                <div class="rpos-floor-canvas"></div>
            </div>
            <div class="rpos-floor-edit-toolbar" style="display:none">
                <button class="rpos-btn rpos-btn-primary" id="rpos-add-table-btn">+ Add Table</button>
                <button class="rpos-btn rpos-btn-success" id="rpos-save-layout-btn">💾 Save Layout</button>
                <button class="rpos-btn rpos-btn-ghost" id="rpos-cancel-edit-btn">Cancel</button>
            </div>
        `);

        this.$tabs   = this.$el.find(".rpos-floor-tabs");
        this.$canvas = this.$el.find(".rpos-floor-canvas");
        this.$editBar = this.$el.find(".rpos-floor-edit-toolbar");

        this.$el.find("#rpos-add-table-btn").on("click", () => this._addTableDialog());
        this.$el.find("#rpos-save-layout-btn").on("click", () => this._saveLayout());
        this.$el.find("#rpos-cancel-edit-btn").on("click", () => this.toggleEditMode(false));
    }

    async refresh() {
        const res = await frappe.call({
            method: "restaurant_pos.api.floor.get_floors",
        });
        this.floors = res.message || [];
        if (!this.floors.length) {
            this.$canvas.html(`
                <div class="rpos-empty-state">
                    <div class="rpos-empty-icon">🍽️</div>
                    <h3>No floors configured</h3>
                    <p>Go to <b>Restaurant POS → Setup</b> to add floors and tables.</p>
                </div>
            `);
            return;
        }
        if (!this.activeFloor || !this.floors.find(f => f.name === this.activeFloor)) {
            this.activeFloor = this.floors[0].name;
        }
        this._renderTabs();
        this._renderCanvas();
        this._updateStats();
    }

    _renderTabs() {
        this.$tabs.empty();
        this.floors.forEach(f => {
            const $tab = $(`<button class="rpos-floor-tab ${f.name === this.activeFloor ? "active" : ""}"
                data-floor="${f.name}">${f.floor_name}</button>`);
            $tab.on("click", () => {
                this.activeFloor = f.name;
                this._renderTabs();
                this._renderCanvas();
                this._updateStats();
            });
            this.$tabs.append($tab);
        });
    }

    _renderCanvas() {
        const floor = this.floors.find(f => f.name === this.activeFloor);
        if (!floor) return;

        this.$canvas.css("background-color", floor.background_color || "#f0f2f5");
        this.$canvas.empty();

        const CELL = 60; // px per grid cell
        const cols = floor.grid_cols || 20;
        const rows = floor.grid_rows || 15;
        this.$canvas.css({ width: cols * CELL, height: rows * CELL, position: "relative" });

        (floor.tables || []).forEach(t => {
            const $tile = this._buildTableTile(t, CELL);
            this.$canvas.append($tile);
            if (this.editMode) this._makeDraggable($tile, t, floor, CELL);
        });
    }

    _buildTableTile(t, CELL) {
        const x = (t.x_pos || 0) * CELL;
        const y = (t.y_pos || 0) * CELL;
        const w = Math.max(1, t.width || 2) * CELL - 6;
        const h = Math.max(1, t.height || 2) * CELL - 6;

        const status  = (t.status || "Available").toLowerCase();
        const isRound = (t.shape === "round");
        const elapsed = t.order_opened_at ? _elapsedMin(t.order_opened_at) : null;
        const total   = t.order_total ? rpos._money(t.order_total) : "";
        const reservationBadge = (t.reservations?.length)
            ? `<div class="rpos-table-res-badge" title="${t.reservations[0].guest_name}">📅</div>` : "";

        const alertClass = t._alert ? "rpos-table-alert" : "";

        const $tile = $(`
            <div class="rpos-table-tile rpos-status-${status} ${isRound ? "rpos-table-round" : ""} ${alertClass}"
                 data-table="${t.name}"
                 data-status="${t.status}"
                 style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;
                        ${t.color ? "border-color:" + t.color + ";" : ""}">
                ${reservationBadge}
                <div class="rpos-table-number">${t.table_number}</div>
                <div class="rpos-table-cap">${t.capacity}👤</div>
                ${t.status === "Occupied" ? `
                    <div class="rpos-table-meta">
                        ${elapsed !== null ? `<span class="rpos-elapsed ${elapsed > 60 ? "warn" : ""}">${elapsed}m</span>` : ""}
                        ${total ? `<span class="rpos-table-total">${total}</span>` : ""}
                    </div>` : ""}
                ${t.status === "Reserved" && t.reservations?.length ? `
                    <div class="rpos-table-guest">${t.reservations[0].guest_name}</div>` : ""}
                <div class="rpos-table-status-label">${t.status}</div>
            </div>
        `);

        if (!this.editMode) {
            $tile.on("click", () => this._onTableClick(t));
            $tile.on("contextmenu", (e) => { e.preventDefault(); this._showTableMenu(t, e); });
            // Long press for mobile
            let pressTimer;
            $tile.on("touchstart", () => { pressTimer = setTimeout(() => this._showTableMenu(t), 600); });
            $tile.on("touchend touchmove", () => clearTimeout(pressTimer));
        }

        return $tile;
    }

    _onTableClick(t) {
        if (t.status === "Available") {
            this.app.showOrder(t);
        } else if (t.status === "Occupied" && t.current_order) {
            this.app.showOrder(t);
        } else if (t.status === "Reserved") {
            // Offer to seat or view reservation
            this._seatReservationPrompt(t);
        } else if (t.status === "Cleaning") {
            frappe.confirm(`Mark Table ${t.table_number} as Available?`, () => {
                frappe.db.set_value("POS Table", t.name, "status", "Available").then(() => this.refresh());
            });
        }
    }

    _seatReservationPrompt(t) {
        const res = t.reservations?.[0];
        if (!res) { this.app.showOrder(t); return; }

        const d = new frappe.ui.Dialog({
            title: `Table ${t.table_number} — Reserved for ${res.guest_name}`,
            fields: [
                { fieldtype: "HTML", options: `
                    <div class="rpos-res-summary">
                        <p>👤 <b>${res.guest_name}</b> &nbsp;|&nbsp; 🕐 ${frappe.datetime.str_to_user(res.reservation_datetime)}
                        &nbsp;|&nbsp; 👥 ${res.covers} covers</p>
                    </div>` },
            ],
            primary_action_label: "Seat Guest",
            primary_action: async () => {
                d.hide();
                await frappe.call({
                    method: "restaurant_pos.api.reservation.seat_reservation",
                    args: { reservation_name: res.name, pos_profile: this.app.posProfile.name },
                });
                this.refresh();
                this.app.showOrder(t);
            },
            secondary_action_label: "Open Order Anyway",
            secondary_action: () => { d.hide(); this.app.showOrder(t); },
        });
        d.show();
    }

    _showTableMenu(t, event) {
        const items = [
            { label: "📝 Open / New Order", action: () => this.app.showOrder(t) },
            { label: "📅 Add Reservation", action: () => new rpos.ReservationDialog(this.app, t.name) },
            { label: "🧹 Mark Cleaning", action: () => {
                frappe.db.set_value("POS Table", t.name, "status", "Cleaning").then(() => this.refresh());
            }},
            { label: "✅ Mark Available", action: () => {
                frappe.db.set_value("POS Table", t.name, "status", "Available").then(() => this.refresh());
            }},
        ];

        const $menu = $(`<div class="rpos-context-menu"></div>`);
        items.forEach(item => {
            $(`<div class="rpos-context-item">${item.label}</div>`)
                .on("click", () => { $menu.remove(); item.action(); })
                .appendTo($menu);
        });

        const pos = event
            ? { top: event.pageY, left: event.pageX }
            : { top: $(`.rpos-table-tile[data-table="${t.name}"]`).offset().top, left: $(`.rpos-table-tile[data-table="${t.name}"]`).offset().left + 80 };

        $menu.css({ top: pos.top, left: pos.left }).appendTo("body");
        setTimeout(() => $(document).one("click", () => $menu.remove()), 50);
    }

    updateTable(tableName, status, extra) {
        const $tile = this.$canvas.find(`.rpos-table-tile[data-table="${tableName}"]`);
        if (!$tile.length) return;
        $tile.attr("data-status", status)
            .removeClass("rpos-status-available rpos-status-occupied rpos-status-reserved rpos-status-cleaning")
            .addClass(`rpos-status-${status.toLowerCase()}`);
        $tile.find(".rpos-table-status-label").text(status);
        this._updateStats();
    }

    markTableAlert(tableName) {
        this.$canvas.find(`.rpos-table-tile[data-table="${tableName}"]`).addClass("rpos-table-alert");
    }

    _updateStats() {
        const all = this.$canvas.find(".rpos-table-tile");
        const count = (s) => all.filter(`[data-status="${s}"]`).length;
        this.$el.find(".cnt-available").text(count("Available"));
        this.$el.find(".cnt-occupied").text(count("Occupied"));
        this.$el.find(".cnt-reserved").text(count("Reserved"));
        this.$el.find(".cnt-cleaning").text(count("Cleaning"));
    }

    toggleEditMode(force) {
        this.editMode = force !== undefined ? force : !this.editMode;
        this.$editBar.toggle(this.editMode);
        this.$el.toggleClass("rpos-edit-mode", this.editMode);
        this._renderCanvas();
    }

    _makeDraggable($tile, t, floor, CELL) {
        let startX, startY, origLeft, origTop;

        $tile.css("cursor", "grab").on("mousedown touchstart", (e) => {
            const touch = e.originalEvent?.touches?.[0] || e;
            startX = touch.pageX;
            startY = touch.pageY;
            origLeft = parseInt($tile.css("left"));
            origTop  = parseInt($tile.css("top"));
            $tile.css("cursor", "grabbing").addClass("dragging");

            const onMove = (me) => {
                const mt = me.originalEvent?.touches?.[0] || me;
                const dx = mt.pageX - startX;
                const dy = mt.pageY - startY;
                const newX = Math.max(0, origLeft + dx);
                const newY = Math.max(0, origTop  + dy);
                $tile.css({ left: newX, top: newY });
            };
            const onUp = (ue) => {
                $tile.css("cursor", "grab").removeClass("dragging");
                const finalLeft = parseInt($tile.css("left"));
                const finalTop  = parseInt($tile.css("top"));
                t.x_pos = Math.round(finalLeft / CELL);
                t.y_pos = Math.round(finalTop  / CELL);
                // Snap to grid
                $tile.css({ left: t.x_pos * CELL, top: t.y_pos * CELL });
                $(document).off("mousemove.drag touchmove.drag mouseup.drag touchend.drag");
            };
            $(document).on("mousemove.drag touchmove.drag", onMove)
                       .on("mouseup.drag touchend.drag", onUp);
            e.preventDefault();
        });
    }

    async _saveLayout() {
        const floor = this.floors.find(f => f.name === this.activeFloor);
        if (!floor) return;

        const tables = floor.tables.map(t => ({
            name:     t.name,
            x_pos:    t.x_pos || 0,
            y_pos:    t.y_pos || 0,
            width:    t.width || 2,
            height:   t.height || 2,
            floor_id: this.activeFloor,
        }));

        await frappe.call({
            method: "restaurant_pos.api.floor.save_table_layout",
            args: { tables: JSON.stringify(tables) },
        });
        frappe.show_alert({ message: "Layout saved", indicator: "green" });
        this.toggleEditMode(false);
    }

    _addTableDialog() {
        const d = new frappe.ui.Dialog({
            title: "Add Table",
            fields: [
                { fieldtype: "Data",    fieldname: "table_number", label: "Table Number", reqd: 1 },
                { fieldtype: "Int",     fieldname: "capacity",     label: "Capacity",     default: 4 },
                { fieldtype: "Select",  fieldname: "shape",        label: "Shape",
                  options: ["square", "rectangle", "round", "booth"], default: "square" },
            ],
            primary_action_label: "Add",
            primary_action: async (values) => {
                await frappe.call({
                    method: "restaurant_pos.api.floor.create_table",
                    args: { floor_id: this.activeFloor, table_number: values.table_number,
                            x_pos: 0, y_pos: 0, capacity: values.capacity, shape: values.shape },
                });
                d.hide();
                this.refresh();
            },
        });
        d.show();
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Order View
// ─────────────────────────────────────────────────────────────────────────────

rpos.OrderView = class {
    constructor(app, $parent) {
        this.app = app;
        this.order = null;
        this.table = null;
        this.items = [];          // all items from active category
        this.categories = [];
        this.activeCategory = null;
        this.$el = $(`<div class="rpos-order-view" style="display:none"></div>`).appendTo($parent);
        this._build();
    }

    show() { this.$el.show(); }
    hide() { this.$el.hide(); }

    _build() {
        this.$el.html(`
            <div class="rpos-order-layout">
                <!-- LEFT: item catalogue -->
                <div class="rpos-catalogue">
                    <div class="rpos-search-bar">
                        <input type="text" class="rpos-search-input" placeholder="🔍 Search items…">
                    </div>
                    <div class="rpos-category-bar"></div>
                    <div class="rpos-item-grid"></div>
                </div>

                <!-- RIGHT: running order -->
                <div class="rpos-sidebar">
                    <div class="rpos-order-header">
                        <div class="rpos-order-title">
                            <span class="rpos-table-label"></span>
                            <span class="rpos-covers-badge"></span>
                        </div>
                        <div class="rpos-order-actions-top">
                            <button class="rpos-btn rpos-btn-sm rpos-btn-ghost" id="rpos-covers-btn">👥 Covers</button>
                            <button class="rpos-btn rpos-btn-sm rpos-btn-ghost" id="rpos-note-btn">📝 Note</button>
                            <button class="rpos-btn rpos-btn-sm rpos-btn-danger" id="rpos-cancel-order-btn">✕ Cancel</button>
                        </div>
                    </div>
                    <div class="rpos-order-items"></div>
                    <div class="rpos-order-footer">
                        <div class="rpos-totals">
                            <div class="rpos-total-row">
                                <span>Subtotal</span><span class="rpos-subtotal">—</span>
                            </div>
                            <div class="rpos-total-row discount-row" style="display:none">
                                <span>Discount</span><span class="rpos-discount-val">—</span>
                            </div>
                            <div class="rpos-total-row rpos-grand-total-row">
                                <span>Total</span><span class="rpos-grand-total">—</span>
                            </div>
                        </div>
                        <div class="rpos-action-bar">
                            <button class="rpos-btn rpos-btn-warning rpos-btn-lg" id="rpos-kitchen-btn">
                                🍳 Send to Kitchen
                            </button>
                            <button class="rpos-btn rpos-btn-ghost rpos-btn-lg" id="rpos-discount-btn">
                                % Discount
                            </button>
                            <button class="rpos-btn rpos-btn-success rpos-btn-lg" id="rpos-pay-btn">
                                💳 Pay
                            </button>
                        </div>
                        <div class="rpos-split-bar">
                            <button class="rpos-btn rpos-btn-ghost rpos-btn-full" id="rpos-split-btn">
                                ✂ Split Bill
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `);

        this.$categoryBar = this.$el.find(".rpos-category-bar");
        this.$itemGrid    = this.$el.find(".rpos-item-grid");
        this.$orderItems  = this.$el.find(".rpos-order-items");
        this.$search      = this.$el.find(".rpos-search-input");

        this.$search.on("input", _debounce(() => this._searchItems(this.$search.val()), 300));

        this.$el.find("#rpos-kitchen-btn").on("click",       () => this._sendToKitchen());
        this.$el.find("#rpos-pay-btn").on("click",           () => this._openPayment());
        this.$el.find("#rpos-split-btn").on("click",         () => this._openSplit());
        this.$el.find("#rpos-cancel-order-btn").on("click",  () => this._cancelOrder());
        this.$el.find("#rpos-discount-btn").on("click",      () => this._openDiscount());
        this.$el.find("#rpos-covers-btn").on("click",        () => this._editCovers());
        this.$el.find("#rpos-note-btn").on("click",          () => this._editNote());
    }

    async load(tableData) {
        this.table = tableData;
        this.$el.find(".rpos-table-label").text(`Table ${tableData.table_number}`);

        // Load categories
        await this._loadCategories();

        // Load or create order
        if (tableData.current_order && tableData.order_status !== "SETTLED") {
            await this._loadOrder(tableData.current_order);
        } else {
            await this._newOrder();
        }
    }

    async _loadCategories() {
        const res = await frappe.call({
            method: "restaurant_pos.api.floor.get_item_groups_for_pos",
            args: { pos_profile: this.app.posProfile.name },
        });
        this.categories = res.message || [];
        this._renderCategoryBar();
        if (this.categories.length) {
            this.activeCategory = this.categories[0];
            await this._loadItems(this.activeCategory);
        }
    }

    _renderCategoryBar() {
        this.$categoryBar.empty();
        // "All" pill
        const $all = $(`<button class="rpos-cat-pill ${!this.activeCategory || this.activeCategory === "__all__" ? "active" : ""}"
             data-cat="__all__">All</button>`);
        $all.on("click", async () => {
            this.activeCategory = "__all__";
            this._renderCategoryBar();
            await this._loadItems("__all__");
        });
        this.$categoryBar.append($all);

        this.categories.forEach(cat => {
            const $pill = $(`<button class="rpos-cat-pill ${cat === this.activeCategory ? "active" : ""}"
                 data-cat="${cat}">${cat}</button>`);
            $pill.on("click", async () => {
                this.activeCategory = cat;
                this._renderCategoryBar();
                await this._loadItems(cat);
            });
            this.$categoryBar.append($pill);
        });
    }

    async _loadItems(category) {
        this.$itemGrid.html(`<div class="rpos-loading">Loading…</div>`);
        const res = await frappe.call({
            method: "restaurant_pos.api.floor.get_items_for_pos",
            args: { pos_profile: this.app.posProfile.name,
                    item_group: category === "__all__" ? null : category },
        });
        this.items = res.message || [];
        this._renderItemGrid(this.items);
    }

    async _searchItems(query) {
        if (!query) { await this._loadItems(this.activeCategory); return; }
        const res = await frappe.call({
            method: "restaurant_pos.api.floor.get_items_for_pos",
            args: { pos_profile: this.app.posProfile.name, search: query },
        });
        this._renderItemGrid(res.message || []);
    }

    _renderItemGrid(items) {
        this.$itemGrid.empty();
        if (!items.length) {
            this.$itemGrid.html(`<div class="rpos-empty-items">No items found</div>`);
            return;
        }
        items.forEach(item => {
            const imgInner = item.image
                ? `<img src="${item.image}" alt="${item.item_name}" class="rpos-item-img" loading="lazy">`
                : `<div class="rpos-item-img-placeholder">${item.item_name.charAt(0).toUpperCase()}</div>`;
            const img = `<div class="rpos-item-img-wrap">${imgInner}</div>`;
            const $card = $(`
                <div class="rpos-item-card" data-code="${item.item_code}" data-rate="${item.rate}">
                    ${img}
                    <div class="rpos-item-name">${item.item_name}</div>
                    <div class="rpos-item-price">${rpos._money(item.rate)}</div>
                </div>
            `);
            $card.on("click", () => this._onItemTap(item));
            this.$itemGrid.append($card);
        });
    }

    async _onItemTap(item) {
        // Check for modifiers first
        const modRes = await frappe.call({
            method: "restaurant_pos.api.modifier.get_item_modifiers",
            args: { item_code: item.item_code },
        });
        const modGroups = modRes.message || [];

        if (modGroups.length) {
            new rpos.ModifierDialog(this.app, item, modGroups, (qty, rate, modifiers, notes) => {
                this._addItemToOrder(item, qty, rate, modifiers, notes);
            });
        } else {
            this._addItemToOrder(item, 1, item.rate, [], "");
        }
    }

    async _addItemToOrder(item, qty, rate, modifiers, notes) {
        if (!this.order) await this._newOrder();

        const res = await frappe.call({
            method: "restaurant_pos.api.order.add_item",
            args: {
                order_name:     this.order.name,
                item_code:      item.item_code,
                qty,
                rate,
                modifiers:      JSON.stringify(modifiers),
                notes:          notes || "",
                client_version: this.order.version,
            },
        });
        if (res.message) {
            this.order = res.message;
            this._renderOrderItems();
        }
    }

    async _newOrder() {
        const res = await frappe.call({
            method: "restaurant_pos.api.order.create_order",
            args: {
                pos_profile: this.app.posProfile.name,
                table_id:    this.table.name,
                guest_count: this.table.capacity || 2,
            },
        });
        this.order = res.message;
        this._renderOrderMeta();
        this._renderOrderItems();
    }

    async _loadOrder(orderName) {
        const res = await frappe.call({
            method: "restaurant_pos.api.order.get_order",
            args: { order_name: orderName },
        });
        this.order = res.message;
        this._renderOrderMeta();
        this._renderOrderItems();
    }

    async refreshOrder() {
        if (!this.order) return;
        await this._loadOrder(this.order.name);
    }

    _renderOrderMeta() {
        if (!this.order) return;
        this.$el.find(".rpos-covers-badge").text(`👥 ${this.order.covers || this.order.guest_count || 1}`);
    }

    _renderOrderItems() {
        if (!this.order) return;
        this.$orderItems.empty();

        const items = this.order.items || [];
        if (!items.length) {
            this.$orderItems.html(`<div class="rpos-empty-order">Tap items to add to order</div>`);
            this._updateTotals(0);
            return;
        }

        items.forEach(item => {
            const statusIcon = { pending:"⏳", sent:"📨", cooking:"🔥", ready:"✅", served:"🍽" }[item.item_status] || "";
            const mods = _parseModifiers(item.modifiers);
            const modsHtml = mods.length
                ? `<div class="rpos-item-mods">${mods.map(m => m.option_name).join(", ")}</div>` : "";
            const canEdit = item.item_status === "pending";

            const $row = $(`
                <div class="rpos-order-row" data-idx="${item.idx}" data-status="${item.item_status}">
                    <div class="rpos-order-row-main">
                        <div class="rpos-order-item-info">
                            <span class="rpos-order-item-name">${item.item_name}</span>
                            ${modsHtml}
                            ${item.notes ? `<div class="rpos-item-note">📝 ${item.notes}</div>` : ""}
                        </div>
                        <div class="rpos-order-item-right">
                            <span class="rpos-item-status-icon">${statusIcon}</span>
                            <div class="rpos-qty-ctrl ${canEdit ? "" : "rpos-qty-locked"}">
                                ${canEdit ? `<button class="rpos-qty-btn rpos-qty-minus" data-idx="${item.idx}">−</button>` : ""}
                                <span class="rpos-qty-val">${item.qty}</span>
                                ${canEdit ? `<button class="rpos-qty-btn rpos-qty-plus" data-idx="${item.idx}">+</button>` : ""}
                            </div>
                            <span class="rpos-item-amount">${rpos._money(item.amount)}</span>
                            ${canEdit ? `<button class="rpos-void-btn" data-idx="${item.idx}" title="Remove">🗑</button>` : ""}
                            ${!canEdit && item.item_status !== "served" ? `<button class="rpos-void-btn rpos-mgr-void" data-idx="${item.idx}" title="Void (manager)">⛔</button>` : ""}
                        </div>
                    </div>
                </div>
            `);

            $row.find(".rpos-qty-minus").on("click", () => this._changeQty(item.idx, item.qty - 1));
            $row.find(".rpos-qty-plus").on("click",  () => this._changeQty(item.idx, item.qty + 1));
            $row.find(".rpos-void-btn:not(.rpos-mgr-void)").on("click", () => this._changeQty(item.idx, 0));
            $row.find(".rpos-mgr-void").on("click", () => this._managerVoid(item));

            if (item.item_status === "ready") {
                const $serve = $(`<button class="rpos-serve-btn" data-idx="${item.idx}">Mark Served</button>`);
                $serve.on("click", async () => {
                    await frappe.call({
                        method: "restaurant_pos.api.kds.mark_item_served",
                        args: { order_name: this.order.name, item_idx: item.idx },
                    });
                    this.refreshOrder();
                });
                $row.append($serve);
            }

            this.$orderItems.append($row);
        });

        const subtotal = items.reduce((s, i) => s + (i.amount || 0), 0);
        this._updateTotals(subtotal);
    }

    _updateTotals(subtotal) {
        if (!this.order) return;
        const disc = parseFloat(this.order.discount_amount || 0);
        const grand = Math.max(0, subtotal - disc);
        this.$el.find(".rpos-subtotal").text(rpos._money(subtotal));
        this.$el.find(".rpos-grand-total").text(rpos._money(grand));
        this.$el.find(".discount-row").toggle(disc > 0);
        if (disc > 0) this.$el.find(".rpos-discount-val").text(`-${rpos._money(disc)}`);
    }

    async _changeQty(idx, qty) {
        const res = await frappe.call({
            method: "restaurant_pos.api.order.update_item_qty",
            args: { order_name: this.order.name, item_idx: idx, qty, client_version: this.order.version },
        });
        if (res.message) { this.order = res.message; this._renderOrderItems(); }
    }

    async _sendToKitchen() {
        const pending = (this.order?.items || []).filter(i => i.item_status === "pending");
        if (!pending.length) { frappe.show_alert({message:"No pending items to send", indicator:"orange"}); return; }

        const res = await frappe.call({
            method: "restaurant_pos.api.order.send_to_kitchen",
            args: { order_name: this.order.name, client_version: this.order.version },
        });
        if (res.message) {
            this.order = res.message;
            this._renderOrderItems();
            frappe.show_alert({message:`🍳 ${pending.length} item(s) sent to kitchen`, indicator:"green"});
        }
    }

    _openPayment() {
        if (!this.order?.items?.length) { frappe.show_alert({message:"Order is empty", indicator:"orange"}); return; }
        this.app.showPayment(this.order);
    }

    _openSplit() {
        if (!this.order) return;
        new rpos.SplitDialog(this.app, this.order, () => this.refreshOrder());
    }

    _openDiscount() {
        const d = new frappe.ui.Dialog({
            title: "Apply Discount",
            fields: [
                { fieldtype: "Select", fieldname: "discount_type", label: "Type",
                  options: ["Fixed Amount", "Percentage"], default: "Fixed Amount" },
                { fieldtype: "Float", fieldname: "discount_value", label: "Value", reqd: 1 },
            ],
            primary_action_label: "Apply",
            primary_action: async (vals) => {
                const subtotal = (this.order.items || []).reduce((s, i) => s + i.amount, 0);
                const disc = vals.discount_type === "Percentage"
                    ? subtotal * vals.discount_value / 100
                    : vals.discount_value;

                await frappe.db.set_value("POS Order", this.order.name, {
                    discount_amount: disc,
                    discount_type: vals.discount_type === "Percentage" ? "Percentage" : "Fixed",
                });
                this.order.discount_amount = disc;
                this._renderOrderItems();
                d.hide();
            },
        });
        d.show();
    }

    _editCovers() {
        frappe.prompt({ fieldtype: "Int", fieldname: "covers", label: "Number of Covers",
                        default: this.order?.covers || 1 },
            async (vals) => {
                await frappe.db.set_value("POS Order", this.order.name, "covers", vals.covers);
                this.order.covers = vals.covers;
                this._renderOrderMeta();
            }, "Edit Covers", "Save");
    }

    _editNote() {
        frappe.prompt({ fieldtype: "Small Text", fieldname: "notes", label: "Order Notes",
                        default: this.order?.notes || "" },
            async (vals) => {
                await frappe.db.set_value("POS Order", this.order.name, "notes", vals.notes);
                this.order.notes = vals.notes;
            }, "Order Note", "Save");
    }

    _cancelOrder() {
        frappe.confirm("Cancel this order? All items will be removed.", async () => {
            await frappe.call({
                method: "restaurant_pos.api.order.cancel_order",
                args: { order_name: this.order.name, reason: "Cancelled by waiter" },
            });
            this.order = null;
            this.app.showFloor();
        });
    }

    _managerVoid(item) {
        const d = new frappe.ui.Dialog({
            title: "Manager Void",
            fields: [
                { fieldtype: "Data",      fieldname: "manager_user",     label: "Manager Username", reqd: 1 },
                { fieldtype: "Password",  fieldname: "manager_password", label: "Password",         reqd: 1 },
                { fieldtype: "Data",      fieldname: "reason",           label: "Reason",           reqd: 1 },
            ],
            primary_action_label: "Void Item",
            primary_action: async (vals) => {
                const res = await frappe.call({
                    method: "restaurant_pos.api.modifier.apply_void",
                    args: {
                        order_name:       this.order.name,
                        item_idx:         item.idx,
                        manager_user:     vals.manager_user,
                        manager_password: vals.manager_password,
                        reason:           vals.reason,
                    },
                });
                if (res.message) { d.hide(); this.refreshOrder(); }
            },
        });
        d.show();
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Payment View
// ─────────────────────────────────────────────────────────────────────────────

rpos.PaymentView = class {
    constructor(app, $parent) {
        this.app = app;
        this.order = null;
        this.preview = null;
        this.payments = {};   // mode → amount
        this.$el = $(`<div class="rpos-payment-view" style="display:none"></div>`).appendTo($parent);
        this._build();
    }

    show(order) {
        this.order = order;
        this.payments = {};
        this.$el.show();
        this._loadPreview();
    }

    hide() { this.$el.hide(); }

    _build() {
        this.$el.html(`
            <div class="rpos-payment-layout">
                <div class="rpos-payment-left">
                    <div class="rpos-payment-header">
                        <button class="rpos-btn rpos-btn-ghost" id="rpos-pay-back">← Back</button>
                        <h2>Payment</h2>
                        <span class="rpos-pay-order-name"></span>
                    </div>
                    <div class="rpos-pay-items"></div>
                    <div class="rpos-pay-summary">
                        <div class="rpos-pay-row"><span>Subtotal</span><span class="rpos-pay-subtotal"></span></div>
                        <div class="rpos-pay-row"><span>Tax</span><span class="rpos-pay-tax"></span></div>
                        <div class="rpos-pay-row rpos-pay-total-row"><span>Total</span><span class="rpos-pay-grand"></span></div>
                    </div>
                </div>
                <div class="rpos-payment-right">
                    <div class="rpos-numpad-area">
                        <div class="rpos-pay-amount-display">
                            <span class="rpos-pay-amount-label">Enter Amount</span>
                            <span class="rpos-pay-amount-val">0</span>
                        </div>
                        <div class="rpos-numpad"></div>
                    </div>
                    <div class="rpos-payment-methods"></div>
                    <div class="rpos-pay-breakdown"></div>
                    <div class="rpos-change-row" style="display:none">
                        <span>Change</span><span class="rpos-change-val"></span>
                    </div>
                    <div class="rpos-pay-actions">
                        <label class="rpos-print-toggle">
                            <input type="checkbox" id="rpos-print-receipt" checked> Print Receipt
                        </label>
                        <button class="rpos-btn rpos-btn-success rpos-btn-xl" id="rpos-confirm-pay">
                            ✓ Confirm Payment
                        </button>
                    </div>
                </div>
            </div>
        `);

        this.$el.find("#rpos-pay-back").on("click", () => this.app.backToOrder());
        this.$el.find("#rpos-confirm-pay").on("click", () => this._confirmPayment());

        this._buildNumpad();
    }

    _buildNumpad() {
        const $np = this.$el.find(".rpos-numpad");
        const keys = ["7","8","9","4","5","6","1","2","3",".",  "0","⌫"];
        keys.forEach(k => {
            const $btn = $(`<button class="rpos-numpad-btn ${k==="0"?"span2":""}">${k}</button>`);
            $btn.on("click", () => this._numpadPress(k));
            $np.append($btn);
        });
    }

    _numpadVal = "0";

    _numpadPress(k) {
        if (k === "⌫") {
            this._numpadVal = this._numpadVal.length > 1 ? this._numpadVal.slice(0, -1) : "0";
        } else if (k === "." && this._numpadVal.includes(".")) {
            return;
        } else if (this._numpadVal === "0" && k !== ".") {
            this._numpadVal = k;
        } else {
            this._numpadVal += k;
        }
        this.$el.find(".rpos-pay-amount-val").text(this._numpadVal);
        this._updateChange();
    }

    async _loadPreview() {
        this.$el.find(".rpos-pay-order-name").text(this.order.name);
        const res = await frappe.call({
            method: "restaurant_pos.api.settlement.get_settlement_preview",
            args: { order_name: this.order.name },
        });
        this.preview = res.message;
        this._renderPreview();
        this._renderPaymentMethods();
    }

    _renderPreview() {
        if (!this.preview) return;
        const { subtotal, tax_amount, grand_total, items } = this.preview;

        this.$el.find(".rpos-pay-subtotal").text(rpos._money(subtotal));
        this.$el.find(".rpos-pay-tax").text(rpos._money(tax_amount));
        this.$el.find(".rpos-pay-grand").text(rpos._money(grand_total));

        const $list = this.$el.find(".rpos-pay-items");
        $list.empty();
        (items || []).forEach(i => {
            $list.append(`<div class="rpos-pay-item-row">
                <span>${i.qty}× ${i.item_name}</span>
                <span>${rpos._money(i.amount)}</span>
            </div>`);
        });

        // Preset numpad to full grand total
        this._numpadVal = String(grand_total);
        this.$el.find(".rpos-pay-amount-val").text(this._numpadVal);
    }

    _renderPaymentMethods() {
        const $methods = this.$el.find(".rpos-payment-methods");
        $methods.empty();
        const methods = this.app.posProfile.payments || ["Cash"];
        methods.forEach(m => {
            const $btn = $(`<button class="rpos-method-btn" data-method="${m}">${_methodIcon(m)} ${m}</button>`);
            $btn.on("click", () => this._selectMethod(m));
            $methods.append($btn);
        });
    }

    _selectMethod(method) {
        const amount = parseFloat(this._numpadVal) || 0;
        const remaining = this._remaining();

        this.payments[method] = (this.payments[method] || 0) + Math.min(amount, remaining);
        this._numpadVal = "0";
        this.$el.find(".rpos-pay-amount-val").text("0");
        this._renderBreakdown();
        this._updateChange();
    }

    _remaining() {
        if (!this.preview) return 0;
        const paid = Object.values(this.payments).reduce((a, b) => a + b, 0);
        return Math.max(0, this.preview.grand_total - paid);
    }

    _renderBreakdown() {
        const $bd = this.$el.find(".rpos-pay-breakdown");
        $bd.empty();
        Object.entries(this.payments).forEach(([m, a]) => {
            const $row = $(`<div class="rpos-pay-bd-row">
                <span>${m}</span>
                <span>${rpos._money(a)}</span>
                <button class="rpos-pay-bd-remove" data-method="${m}">✕</button>
            </div>`);
            $row.find(".rpos-pay-bd-remove").on("click", () => {
                delete this.payments[m];
                this._renderBreakdown();
                this._updateChange();
            });
            $bd.append($row);
        });
    }

    _updateChange() {
        if (!this.preview) return;
        const paid = Object.values(this.payments).reduce((a, b) => a + b, 0);
        const change = paid - this.preview.grand_total;
        this.$el.find(".rpos-change-row").toggle(change > 0);
        this.$el.find(".rpos-change-val").text(rpos._money(change));
    }

    async _confirmPayment() {
        if (!this.preview) return;
        const paid  = Object.values(this.payments).reduce((a, b) => a + b, 0);
        const total = this.preview.grand_total;

        if (paid < total - 0.01) {
            frappe.show_alert({ message: `Under-paid by ${rpos._money(total - paid)}`, indicator: "red" });
            return;
        }
        if (!Object.keys(this.payments).length) {
            frappe.show_alert({ message: "Select a payment method", indicator: "orange" });
            return;
        }

        const $btn = this.$el.find("#rpos-confirm-pay").prop("disabled", true).text("Processing…");

        try {
            const payArr = Object.entries(this.payments).map(([m, a]) => ({
                mode_of_payment: m, amount: a,
            }));
            const res = await frappe.call({
                method: "restaurant_pos.api.settlement.settle_order",
                args: {
                    order_name:     this.order.name,
                    payments:       JSON.stringify(payArr),
                    client_version: this.order.version,
                },
            });

            if (res.message) {
                frappe.show_alert({ message: `✅ Payment complete — ${res.message.invoice}`, indicator: "green" });

                if (this.$el.find("#rpos-print-receipt").is(":checked")) {
                    rpos.Printer.printReceipt(res.message.invoice);
                }
                this.app.showFloor();
                this.app.floorView.refresh();
            }
        } catch (err) {
            frappe.show_alert({ message: err.message || "Payment failed", indicator: "red" });
        } finally {
            $btn.prop("disabled", false).html("✓ Confirm Payment");
        }
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Modifier Dialog
// ─────────────────────────────────────────────────────────────────────────────

rpos.ModifierDialog = class {
    constructor(app, item, modGroups, onConfirm) {
        this.app       = app;
        this.item      = item;
        this.modGroups = modGroups;
        this.onConfirm = onConfirm;
        this.selected  = {};  // groupName → [optionName, ...]
        this.qty       = 1;
        this.notes     = "";

        // Pre-select defaults
        modGroups.forEach(g => {
            const defaults = g.options.filter(o => o.is_default).map(o => o.option_name);
            if (defaults.length) this.selected[g.name] = defaults;
        });

        this._show();
    }

    _show() {
        const modHtml = this.modGroups.map(g => `
            <div class="rpos-mod-group">
                <div class="rpos-mod-group-title">
                    ${g.group_name}
                    ${g.is_required ? '<span class="rpos-required-badge">Required</span>' : ""}
                    ${g.max_selections > 1 || g.max_selections === 0
                        ? `<span class="rpos-multi-badge">Choose up to ${g.max_selections || "∞"}</span>` : ""}
                </div>
                <div class="rpos-mod-options">
                    ${g.options.map(o => {
                        const price = o.price_adjustment
                            ? ` <span class="rpos-mod-price">${o.price_adjustment > 0 ? "+" : ""}${rpos._money(o.price_adjustment)}</span>`
                            : "";
                        return `<div class="rpos-mod-option" data-group="${g.name}" data-option="${o.option_name}" data-price="${o.price_adjustment || 0}">
                            <span>${o.option_name}</span>${price}
                        </div>`;
                    }).join("")}
                </div>
            </div>
        `).join("");

        const d = new frappe.ui.Dialog({
            title: `${this.item.item_name}`,
            fields: [
                { fieldtype: "HTML", options: `
                    <div class="rpos-modifier-dialog">
                        ${this.item.image ? `<img src="${this.item.image}" class="rpos-mod-item-img">` : ""}
                        <div class="rpos-mod-base-price">
                            Base: ${rpos._money(this.item.rate)}
                        </div>
                        ${modHtml}
                        <div class="rpos-mod-footer">
                            <div class="rpos-mod-qty">
                                <button class="rpos-qty-btn" id="rpos-mod-minus">−</button>
                                <span class="rpos-mod-qty-val">1</span>
                                <button class="rpos-qty-btn" id="rpos-mod-plus">+</button>
                            </div>
                            <div class="rpos-mod-notes">
                                <input type="text" class="rpos-mod-notes-input" placeholder="Special instructions…">
                            </div>
                            <div class="rpos-mod-total">
                                Total: <b class="rpos-mod-total-val">${rpos._money(this.item.rate)}</b>
                            </div>
                        </div>
                    </div>
                `},
            ],
            primary_action_label: "Add to Order",
            primary_action: () => {
                if (!this._validate()) return;
                const mods = this._buildModifierList();
                const adjTotal = mods.reduce((s, m) => s + (m.price_adjustment || 0), 0);
                const effectiveRate = this.item.rate + adjTotal;
                this.onConfirm(this.qty, effectiveRate, mods, this.notes);
                d.hide();
            },
        });

        d.show();

        const $body = d.$wrapper.find(".rpos-modifier-dialog");

        // Option selection
        $body.on("click", ".rpos-mod-option", (e) => {
            const $opt   = $(e.currentTarget);
            const gname  = $opt.data("group");
            const oname  = $opt.data("option");
            const group  = this.modGroups.find(g => g.name === gname);
            const maxSel = group.max_selections || 1;

            const cur = this.selected[gname] || [];
            const idx = cur.indexOf(oname);

            if (idx >= 0) {
                this.selected[gname] = cur.filter(x => x !== oname);
            } else {
                if (maxSel === 1) {
                    this.selected[gname] = [oname];
                } else if (maxSel === 0 || cur.length < maxSel) {
                    this.selected[gname] = [...cur, oname];
                }
            }
            this._refreshOptions($body);
            this._refreshTotal($body);
        });

        // Qty
        $body.find("#rpos-mod-minus").on("click", () => {
            if (this.qty > 1) { this.qty--; $body.find(".rpos-mod-qty-val").text(this.qty); this._refreshTotal($body); }
        });
        $body.find("#rpos-mod-plus").on("click", () => {
            this.qty++; $body.find(".rpos-mod-qty-val").text(this.qty); this._refreshTotal($body);
        });

        $body.find(".rpos-mod-notes-input").on("input", (e) => { this.notes = e.target.value; });

        this._refreshOptions($body);
    }

    _refreshOptions($body) {
        $body.find(".rpos-mod-option").each((_, el) => {
            const $o = $(el);
            const gname = $o.data("group");
            const oname = $o.data("option");
            const active = (this.selected[gname] || []).includes(oname);
            $o.toggleClass("selected", active);
        });
    }

    _refreshTotal($body) {
        const adj = this._buildModifierList().reduce((s, m) => s + (m.price_adjustment || 0), 0);
        const total = (this.item.rate + adj) * this.qty;
        $body.find(".rpos-mod-total-val").text(rpos._money(total));
    }

    _validate() {
        for (const g of this.modGroups) {
            if (g.is_required) {
                const sel = this.selected[g.name] || [];
                const min = g.min_selections || 1;
                if (sel.length < min) {
                    frappe.show_alert({ message: `Please select "${g.group_name}"`, indicator: "orange" });
                    return false;
                }
            }
        }
        return true;
    }

    _buildModifierList() {
        const list = [];
        Object.entries(this.selected).forEach(([gname, opts]) => {
            const group = this.modGroups.find(g => g.name === gname);
            opts.forEach(oname => {
                const opt = group?.options.find(o => o.option_name === oname);
                if (opt) list.push({ group: group.group_name, option_name: oname, price_adjustment: opt.price_adjustment || 0 });
            });
        });
        return list;
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Reservation Dialogs
// ─────────────────────────────────────────────────────────────────────────────

rpos.ReservationDialog = class {
    constructor(app, tableId) {
        this.app     = app;
        this.tableId = tableId;
        this._show();
    }

    _show() {
        const d = new frappe.ui.Dialog({
            title: "New Reservation",
            fields: [
                { fieldtype: "Data",     fieldname: "guest_name",           label: "Guest Name",    reqd: 1 },
                { fieldtype: "Data",     fieldname: "phone",                label: "Phone" },
                { fieldtype: "Data",     fieldname: "email",                label: "Email" },
                { fieldtype: "Column Break" },
                { fieldtype: "Int",      fieldname: "covers",               label: "Covers",        default: 2 },
                { fieldtype: "Select",   fieldname: "source",               label: "Source",
                  options: ["Phone", "Walk-in", "Online", "Third-party", "Other"], default: "Phone" },
                { fieldtype: "Section Break" },
                { fieldtype: "Link",     fieldname: "table_id",             label: "Table",
                  options: "POS Table",  default: this.tableId },
                { fieldtype: "Datetime", fieldname: "reservation_datetime", label: "Date & Time",  reqd: 1 },
                { fieldtype: "Section Break" },
                { fieldtype: "Small Text", fieldname: "notes",              label: "Notes" },
            ],
            primary_action_label: "Confirm Reservation",
            primary_action: async (vals) => {
                await frappe.call({
                    method: "restaurant_pos.api.reservation.create_reservation",
                    args: {
                        table_id:             vals.table_id || this.tableId,
                        guest_name:           vals.guest_name,
                        reservation_datetime: vals.reservation_datetime,
                        covers:               vals.covers || 2,
                        phone:                vals.phone || "",
                        email:                vals.email || "",
                        notes:                vals.notes || "",
                        source:               vals.source || "Phone",
                    },
                });
                frappe.show_alert({ message: `Reservation for ${vals.guest_name} confirmed`, indicator: "green" });
                d.hide();
                if (this.app.floorView) this.app.floorView.refresh();
            },
        });
        d.show();
    }
};

rpos.ReservationListDialog = class {
    constructor(app) {
        this.app = app;
        this._show();
    }

    async _show() {
        const res = await frappe.call({
            method: "restaurant_pos.api.reservation.get_reservations",
        });
        const reservations = res.message || [];

        const rows = reservations.length
            ? reservations.map(r => `
                <tr class="rpos-res-row rpos-res-${r.status.toLowerCase().replace("-","")}"
                    data-name="${r.name}">
                    <td>${frappe.datetime.str_to_user(r.reservation_datetime)}</td>
                    <td><b>${r.guest_name}</b></td>
                    <td>${r.table_id || "—"}</td>
                    <td>${r.covers}</td>
                    <td><span class="rpos-res-status-badge">${r.status}</span></td>
                    <td>
                        ${r.status === "Confirmed"
                            ? `<button class="rpos-btn rpos-btn-sm rpos-btn-danger rpos-cancel-res" data-name="${r.name}">Cancel</button>` : ""}
                    </td>
                </tr>`).join("")
            : `<tr><td colspan="6" style="text-align:center;padding:2rem">No reservations today</td></tr>`;

        const d = new frappe.ui.Dialog({
            title: "Today's Reservations",
            size: "large",
            fields: [{
                fieldtype: "HTML",
                options: `
                    <div style="display:flex;justify-content:flex-end;margin-bottom:0.75rem">
                        <button class="rpos-btn rpos-btn-primary" id="rpos-new-res-btn">+ New Reservation</button>
                    </div>
                    <table class="rpos-res-table">
                        <thead><tr>
                            <th>Time</th><th>Guest</th><th>Table</th><th>Covers</th><th>Status</th><th></th>
                        </tr></thead>
                        <tbody>${rows}</tbody>
                    </table>`,
            }],
        });

        d.show();

        d.$wrapper.find("#rpos-new-res-btn").on("click", () => {
            d.hide(); new rpos.ReservationDialog(this.app, null);
        });

        d.$wrapper.on("click", ".rpos-cancel-res", async (e) => {
            const name = $(e.currentTarget).data("name");
            frappe.confirm("Cancel this reservation?", async () => {
                await frappe.call({
                    method: "restaurant_pos.api.reservation.cancel_reservation",
                    args: { reservation_name: name },
                });
                d.hide();
                if (this.app.floorView) this.app.floorView.refresh();
            });
        });
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Split Bill Dialog  (wraps the existing split API)
// ─────────────────────────────────────────────────────────────────────────────

rpos.SplitDialog = class {
    constructor(app, order, onDone) {
        this.app    = app;
        this.order  = order;
        this.onDone = onDone;
        this.buckets = [{ name: "Bill A", items: [] }, { name: "Bill B", items: [] }];
        this._show();
    }

    _show() {
        const itemRows = (this.order.items || []).map(item => `
            <div class="rpos-split-item" data-idx="${item.idx}" data-qty="${item.qty}" data-rate="${item.rate}">
                <div class="rpos-split-item-info">
                    <span>${item.item_name}</span>
                    <span class="rpos-split-qty">×${item.qty}</span>
                    <span class="rpos-split-amt">${rpos._money(item.amount)}</span>
                </div>
                <div class="rpos-split-item-btns">
                    ${this.buckets.map((b, i) => `
                        <button class="rpos-btn rpos-btn-sm rpos-split-assign" data-bucket="${i}"
                            data-idx="${item.idx}">${b.name}</button>`).join("")}
                </div>
            </div>`).join("");

        const d = new frappe.ui.Dialog({
            title: "Split Bill",
            size: "large",
            fields: [{
                fieldtype: "HTML",
                options: `
                    <div class="rpos-split-dialog">
                        <div class="rpos-split-items-col">
                            <h4>Items</h4>
                            <div class="rpos-split-items">${itemRows}</div>
                        </div>
                        <div class="rpos-split-buckets-col">
                            <h4>Bills</h4>
                            <div class="rpos-split-buckets"></div>
                            <button class="rpos-btn rpos-btn-ghost" id="rpos-add-bucket">+ Add Bill</button>
                        </div>
                    </div>`,
            }],
            primary_action_label: "Confirm Split",
            primary_action: async () => {
                await this._confirmSplit();
                d.hide();
            },
        });

        d.show();
        this._renderBuckets(d.$wrapper);

        d.$wrapper.on("click", ".rpos-split-assign", (e) => {
            const idx    = parseInt($(e.currentTarget).data("idx"));
            const bucket = parseInt($(e.currentTarget).data("bucket"));
            const qty    = parseFloat($(e.currentTarget).closest(".rpos-split-item").data("qty"));
            this.buckets[bucket].items.push({ item_idx: idx, qty });
            $(e.currentTarget).addClass("assigned");
            this._renderBuckets(d.$wrapper);
        });

        d.$wrapper.find("#rpos-add-bucket").on("click", () => {
            this.buckets.push({ name: `Bill ${String.fromCharCode(65 + this.buckets.length)}`, items: [] });
            d.$wrapper.find(".rpos-split-items .rpos-split-item").each((_, el) => {
                const idx = $(el).data("idx");
                const qty = $(el).data("qty");
                $(el).find(".rpos-split-item-btns").append(
                    `<button class="rpos-btn rpos-btn-sm rpos-split-assign" data-bucket="${this.buckets.length-1}"
                        data-idx="${idx}">Bill ${String.fromCharCode(65 + this.buckets.length-1)}</button>`
                );
            });
            this._renderBuckets(d.$wrapper);
        });
    }

    _renderBuckets($wrap) {
        const $col = $wrap.find(".rpos-split-buckets");
        $col.empty();
        this.buckets.forEach((b, i) => {
            const total = b.items.reduce((s, bi) => {
                const src = (this.order.items || []).find(x => x.idx === bi.item_idx);
                return s + (src ? src.rate * bi.qty : 0);
            }, 0);
            $col.append(`
                <div class="rpos-bucket">
                    <div class="rpos-bucket-header">
                        <b>${b.name}</b>
                        <span>${rpos._money(total)}</span>
                    </div>
                    ${b.items.map(bi => {
                        const src = (this.order.items || []).find(x => x.idx === bi.item_idx);
                        return src ? `<div class="rpos-bucket-item">${src.item_name} ×${bi.qty}</div>` : "";
                    }).join("")}
                </div>`);
        });
    }

    async _confirmSplit() {
        await frappe.call({
            method: "restaurant_pos.api.split.start_split",
            args: { order_name: this.order.name, client_version: this.order.version },
        });

        const validBuckets = this.buckets.filter(b => b.items.length);
        await frappe.call({
            method: "restaurant_pos.api.split.create_split_plan",
            args: {
                order_name:   this.order.name,
                split_config: JSON.stringify({
                    type:   "item_split",
                    splits: validBuckets.map(b => ({ name: b.name, items: b.items })),
                }),
            },
        });

        frappe.show_alert({ message: "Split created — settle each bill separately", indicator: "green" });
        this.onDone();
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  Printer
// ─────────────────────────────────────────────────────────────────────────────

rpos.Printer = {
    printReceipt(invoiceName) {
        const url = frappe.urllib.get_full_url(
            `/api/method/frappe.utils.print_format.download_pdf?doctype=POS%20Invoice&name=${encodeURIComponent(invoiceName)}&format=POS%20Invoice&no_letterhead=0`
        );
        const win = window.open(url, "_blank");
        if (win) {
            win.onload = () => { win.print(); };
        }
    },

    printKitchenTicket(orderName, station) {
        frappe.show_alert({ message: `🖨 Kitchen ticket: ${station}`, indicator: "blue" });
        // Extend: call a dedicated print format or ESC/POS bridge
    },
};

// ─────────────────────────────────────────────────────────────────────────────
//  Utilities
// ─────────────────────────────────────────────────────────────────────────────

function _elapsedMin(datetimeStr) {
    if (!datetimeStr) return null;
    const d = new Date(datetimeStr.replace(" ", "T"));
    return Math.floor((Date.now() - d.getTime()) / 60000);
}

function _parseModifiers(json_str) {
    try { return JSON.parse(json_str) || []; } catch (_) { return []; }
}

function _debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function _methodIcon(method) {
    const icons = { Cash: "💵", "Credit Card": "💳", Card: "💳", Online: "📱", Voucher: "🎫" };
    return icons[method] || "💰";
}
