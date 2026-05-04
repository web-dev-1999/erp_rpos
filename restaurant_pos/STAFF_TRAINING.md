# Restaurant POS — Staff Training Guide

**Version:** 1.0  
**System:** Restaurant POS (powered by ERPNext)  
**Audience:** Waiters, Cashiers, Managers, Kitchen Staff

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Roles & Access](#2-roles--access)
3. [Waiter Guide — Floor & Orders](#3-waiter-guide--floor--orders)
4. [Waiter Guide — Payment & Bill Splitting](#4-waiter-guide--payment--bill-splitting)
5. [Reservation Management](#5-reservation-management)
6. [Kitchen Display System (KDS)](#6-kitchen-display-system-kds)
7. [Manager Functions](#7-manager-functions)
8. [Common Scenarios & Tips](#8-common-scenarios--tips)
9. [Quick Reference Card](#9-quick-reference-card)

---

## 1. System Overview

The Restaurant POS is a full-screen application accessed from any browser at:

```
http://[your-server]/desk/rpos        ← Waiter / Cashier POS
http://[your-server]/desk/kds         ← Kitchen Display
```

The system is divided into three connected parts:

| Screen | Who Uses It | Purpose |
|--------|-------------|---------|
| **Floor Plan** | Waiter | See all tables, their status, and reservations |
| **Order Screen** | Waiter / Cashier | Add items, send to kitchen, apply discounts |
| **Kitchen Display (KDS)** | Kitchen Staff | See and action incoming orders |

Everything updates in **real time** — when a waiter sends an order, the kitchen sees it instantly. When kitchen marks an item ready, the waiter's screen updates automatically.

---

## 2. Roles & Access

| Role | What They Can Do |
|------|-----------------|
| **POS Cashier** | Open tables, take orders, send to kitchen, process payment |
| **POS Manager** | Everything above + void sent items, apply discounts, edit floor layout |
| **Kitchen Staff** | View and advance item status on the KDS screen |
| **System Manager** | Full access including setup and configuration |

> **Login:** Use your ERPNext username and password. The system will show only the features your role allows.

---

## 3. Waiter Guide — Floor & Orders

### 3.1 The Floor Plan

When you open the POS, you land on the **Floor Plan**. This is your command centre.

**Table colours at a glance:**

| Colour | Status | What to do |
|--------|--------|-----------|
| 🟢 Green | Available | Tap to open a new order |
| 🟠 Amber | Occupied | Tap to view the running order |
| 🔵 Blue | Reserved | A booking is waiting — tap to seat the guest |
| 🟣 Purple | Cleaning | Tap and confirm to mark it Available |

**The numbers on each table:**
- **Large number** = table number
- **👤 number** = seat capacity
- **Time (e.g. 45m)** = how long the table has been occupied — turns red after 60 minutes
- **Amount** = current order total

**Multiple floors / areas:** Use the tabs at the top (e.g. *Main Floor*, *Terrace*, *Private Dining*) to switch between areas.

**Stats bar:** Shows a live count of Available / Occupied / Reserved / Cleaning tables across the current floor.

---

### 3.2 Opening a Table

1. Tap any **green (Available)** table.
2. The Order Screen opens automatically with a new order.
3. The table turns **amber** and is now marked Occupied in real time.

---

### 3.3 Adding Items to an Order

The Order Screen has two panels:

- **Left panel** — Item catalogue (tap to add)
- **Right panel** — Running order (your bill in progress)

**Step-by-step:**

1. Use the **category pills** across the top to filter by food type (Starters, Mains, Drinks, Desserts, etc.).
2. Tap any **item card** to add it.
3. If the item has **modifiers** (e.g. steak doneness, sauce choice), a pop-up appears:
   - Required choices are marked **Required** in red — you must select one.
   - Optional extras show a price adjustment (e.g. +150).
   - Set the **quantity** using − / + at the bottom.
   - Add **special instructions** in the notes field (e.g. "no onions").
   - Tap **Add to Order**.
4. The item appears in the right panel with status ⏳ *pending*.

**Search:** Use the search bar at the top of the catalogue to find items by name or code instantly.

---

### 3.4 Editing the Order Before Sending

While items are still **pending** (⏳), you can:

| Action | How |
|--------|-----|
| Increase quantity | Tap **+** next to the item |
| Decrease quantity | Tap **−** next to the item |
| Remove item | Tap the 🗑 bin icon |
| Update covers (guests) | Tap **👥 Covers** button |
| Add an order note | Tap **📝 Note** button |

---

### 3.5 Sending to Kitchen

When the guest is done ordering, tap the **🍳 Send to Kitchen** button.

- All pending items are sent simultaneously.
- Their status changes to 📨 *Sent*.
- The kitchen sees the ticket on the KDS screen immediately.
- You **cannot delete** sent items without manager approval (see [Void](#7-manager-functions)).

You can add more items after sending — just tap them and send again. The kitchen receives the new items as a fresh ticket.

---

### 3.6 Tracking Item Status

Items move through these stages:

| Icon | Status | Meaning |
|------|--------|---------|
| ⏳ | Pending | Not yet sent to kitchen |
| 📨 | Sent | Kitchen has received it |
| 🔥 | Cooking | Kitchen has started preparation |
| ✅ | Ready | Kitchen has finished — go collect! |
| 🍽 | Served | You have delivered it to the guest |

When an item is **Ready (✅)**, a green **"Mark Served"** button appears on the order. Tap it after you deliver the dish.

---

### 3.7 Right-Click / Long-Press Menu

On **desktop:** right-click any table tile for a quick menu.  
On **tablet:** hold your finger on a table tile for ~0.6 seconds.

Options:
- 📝 Open / New Order
- 📅 Add Reservation
- 🧹 Mark Cleaning
- ✅ Mark Available

---

## 4. Waiter Guide — Payment & Bill Splitting

### 4.1 Standard Payment

1. From the Order Screen, tap **💳 Pay**.
2. The Payment Screen shows the full itemised bill with tax.
3. On the **right side**, enter the amount the guest is paying using the numpad.
4. Tap the payment method button (**Cash**, **Credit Card**, **Online**, etc.).
5. If the guest pays the exact amount, skip the numpad — just tap the payment method.
6. **Change** is calculated automatically and shown in green.
7. For mixed payments (e.g. part cash, part card):
   - Enter the cash amount → tap Cash
   - Enter the card amount → tap Credit Card
   - Repeat until the total is fully covered
8. Toggle **Print Receipt** if you want a printed receipt.
9. Tap **✓ Confirm Payment**.

The table resets to Available automatically.

---

### 4.2 Bill Splitting

1. From the Order Screen, tap **✂ Split Bill**.
2. The Split dialog shows all items on the left.
3. Assign each item to a bill (Bill A, Bill B, etc.) by tapping the bill button next to it.
4. Tap **+ Add Bill** if there are more than two guests paying separately.
5. Tap **Confirm Split**.
6. Settle each bill separately through the normal payment flow.

---

### 4.3 Applying a Discount

1. From the Order Screen, tap **% Discount**.
2. Choose **Fixed Amount** (e.g. deduct 200) or **Percentage** (e.g. 10%).
3. Enter the value and tap **Apply**.
4. The discount appears on the bill and is deducted from the total.

> **Note:** Only managers may authorise discounts at certain venues — check with your manager if the option is restricted.

---

## 5. Reservation Management

### 5.1 Viewing Today's Reservations

Tap **📅 Reservations** in the top-right header from any screen.

The list shows all of today's reservations with guest name, table, time, covers, and status.

---

### 5.2 Creating a Reservation

**From the Reservations list:**
1. Tap **+ New Reservation**.
2. Fill in: Guest Name, Phone, Covers, Table, Date & Time, Source (Phone / Walk-in / Online).
3. Tap **Confirm Reservation**.

**From a table on the floor:**
1. Right-click (or long-press) a table.
2. Select **📅 Add Reservation**.
3. Fill in the form.

The table turns **blue (Reserved)** immediately.

---

### 5.3 Seating a Reserved Guest

1. Tap the **blue (Reserved)** table.
2. A pop-up shows the guest details (name, time, covers).
3. Tap **Seat Guest** — this creates an order automatically linked to the reservation.
4. The table turns amber and the order is ready.

---

### 5.4 Auto-Release Notifications

If a reserved table has not been seated within **60 minutes** of the reservation time, the system automatically alerts the waiter with an orange notification badge on the table.

If the table is **still not seated 30 minutes after the alert**, the system marks the reservation as **No-Show** and releases the table back to Available.

---

### 5.5 Cancelling a Reservation

1. Open **📅 Reservations**.
2. Find the reservation and tap **Cancel**.
3. Confirm the cancellation.

The table is released if no other reservations are active for it.

---

## 6. Kitchen Display System (KDS)

Access the KDS on the kitchen screen at: `http://[your-server]/desk/kds`

### 6.1 Reading the KDS

- Each **column** is a kitchen station (e.g. Grill, Cold Kitchen, Desserts).
- Each **ticket** is one table's order.
- Each **chip** inside a ticket is one item.

Chip colours:
| Colour | Status |
|--------|--------|
| Blue | Sent — not yet started |
| Orange | Cooking — in progress |
| Green | Ready — waiting for collection |

---

### 6.2 Advancing Item Status

Tap the **▶ arrow button** on any item chip to advance it:

```
Sent → Cooking → Ready
```

When all items on a ticket are **Ready**, the ticket fades out automatically after a few seconds.

---

### 6.3 Refreshing the Queue

If the display ever looks out of date, tap **Refresh** in the top toolbar.

---

## 7. Manager Functions

### 7.1 Voiding a Sent Item

If a guest changes their mind after an item has been sent to the kitchen:

1. On the Order Screen, tap the ⛔ button next to the item (this appears on sent/cooking/ready items).
2. The Manager Void dialog opens.
3. The **manager** enters their username, password, and a reason.
4. Tap **Void Item**.

The item is removed and an audit record is created automatically.

---

### 7.2 Editing the Floor Layout

1. Tap **✏️ Edit Floor** in the top-right header.
2. Tables become draggable — drag them to new positions.
3. Tap **+ Add Table** to create a new table.
4. Tap **💾 Save Layout** when done.
5. Tap **Cancel** to discard changes.

---

### 7.3 Setting Up Floors

Floors are configured in the back office:

1. Go to **ERPNext → Restaurant POS → POS Floor**.
2. Create a new Floor record (name, grid size, background colour).
3. Tables are then assigned to floors via **POS Table**.

---

## 8. Common Scenarios & Tips

### Scenario: Guest wants to add items after order was sent

Tap the occupied table → tap the items you want to add → tap **🍳 Send to Kitchen** again. The kitchen receives only the new items.

---

### Scenario: Wrong item sent to kitchen

Ask your manager to void it using the ⛔ button. The manager must enter their credentials and a reason.

---

### Scenario: Table needs cleaning after guests leave

Right-click (or long-press) the table → **🧹 Mark Cleaning**. The table turns purple. When cleaning is done, tap it again and confirm to mark it Available.

---

### Scenario: Guest pays with two different methods

On the Payment Screen: enter the cash amount → tap **Cash** → enter the card amount → tap **Credit Card**. The system tracks both and shows any change due.

---

### Scenario: Split bill between friends

Tap **✂ Split Bill** → assign each item to a person → tap **Confirm Split** → settle each bill separately.

---

### Scenario: Reservation guest arrives early / late

Tap the reserved (blue) table → tap **Seat Guest**. The order links automatically to the reservation. If seating is delayed, the system will notify you via an alert badge.

---

### Scenario: KDS screen goes blank

Tap **Refresh** in the KDS toolbar. If items are still missing, the waiter should re-tap **🍳 Send to Kitchen** — items already sent will not duplicate (they show as already in the queue).

---

### Tips for Speed

- Use the **search bar** to find items faster than browsing categories.
- **Long-press** tables on a tablet instead of right-clicking for the quick action menu.
- The **elapsed time** shown on occupied tables turns red at 60 minutes — use it to prioritise check-ins.
- **Covers** (guest count) is automatically set from the table capacity; update it via the 👥 button for accurate reports.

---

## 9. Quick Reference Card

*(Print and laminate for staff)*

---

### 🟢 Open a Table
Tap green table → items appear on left → tap to add → **Send to Kitchen**

### 🍳 Send to Kitchen
Order Screen → **🍳 Send to Kitchen** button (orange)

### 💳 Pay
Order Screen → **💳 Pay** → enter amount → tap method → **✓ Confirm**

### ✂ Split Bill
Order Screen → **✂ Split Bill** → assign items → settle each bill

### % Discount
Order Screen → **% Discount** → choose type & amount → Apply

### 📅 Reserve a Table
Header → **📅 Reservations** → **+ New Reservation** → fill form

### ⛔ Void an Item (Manager Required)
Order Screen → tap ⛔ on sent item → manager enters credentials

### 🧹 Mark Table for Cleaning
Long-press table → **🧹 Mark Cleaning**

### KDS: Advance Item
Tap **▶** on item chip → Sent → Cooking → Ready

---

**Table Status Legend**

| 🟢 Green | 🟠 Amber | 🔵 Blue | 🟣 Purple |
|----------|---------|--------|---------|
| Available | Occupied | Reserved | Cleaning |

---

*For technical issues or system access problems, contact your system administrator.*  
*Powered by ILI Digital Restaurant POS*
