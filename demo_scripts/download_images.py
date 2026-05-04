"""Download food images from Pexels CDN and assign them to Item records."""
import frappe
import os
import urllib.request
import urllib.error

frappe.init(site="frontend")
frappe.connect()

IMG_DIR = "/home/frappe/frappe-bench/sites/frontend/public/files/pos_images"
os.makedirs(IMG_DIR, exist_ok=True)

# Pexels photo IDs mapped to item codes
ITEM_IMAGES = {
    "FOOD-ST-001": (1618898,  "hummus"),
    "FOOD-ST-002": (15801007, "calamari"),
    "FOOD-ST-003": (29173114, "chicken-tikka"),
    "FOOD-ST-004": (3743537,  "garden-salad"),
    "FOOD-ST-005": (8251537,  "caesar-salad"),
    "FOOD-ST-006": (3743537,  "fattoush-salad"),
    "FOOD-ST-007": (4103375,  "mushroom-soup"),
    "FOOD-ST-008": (2532442,  "chicken-soup"),
    "FOOD-ST-009": (7432991,  "bruschetta"),
    "FOOD-ST-010": (3569706,  "spring-rolls"),
    "FOOD-MN-001": (9219086,  "grilled-chicken"),
    "FOOD-MN-002": (769289,   "beef-steak"),
    "FOOD-MN-003": (11795607, "lamb-chops"),
    "FOOD-MN-004": (8352799,  "sea-bass"),
    "FOOD-MN-005": (2092906,  "shrimp-pasta"),
    "FOOD-MN-006": (4224314,  "chicken-biryani"),
    "FOOD-MN-007": (1552641,  "beef-burger"),
    "FOOD-MN-008": (959922,   "club-sandwich"),
    "FOOD-MN-009": (14590497, "margherita-pizza"),
    "FOOD-MN-010": (11220209, "alfredo-pasta"),
    "FOOD-MN-011": (674574,   "vegetable-curry"),
    "FOOD-MN-012": (1516415,  "salmon-fillet"),
    "FOOD-MN-013": (36734922, "mixed-grill"),
    "FOOD-MN-014": (9624298,  "chicken-wrap"),
    "FOOD-MN-015": (36841078, "pasta-arrabiata"),
    "FOOD-BV-001": (3642,     "orange-juice"),
    "FOOD-BV-002": (4021987,  "lemon-mint"),
    "FOOD-BV-003": (14509267, "mango-lassi"),
    "FOOD-BV-004": (8879626,  "cola"),
    "FOOD-BV-005": (327090,   "mineral-water"),
    "FOOD-BV-006": (13887363, "sparkling-water"),
    "FOOD-BV-007": (230477,   "hot-tea"),
    "FOOD-BV-008": (19026101, "espresso"),
    "FOOD-BV-009": (2396220,  "cappuccino"),
    "FOOD-BV-010": (3410323,  "strawberry-juice"),
    "FOOD-BV-011": (3309670,  "hot-chocolate"),
    "FOOD-BV-012": (39587,    "lemonade"),
    "FOOD-DS-001": (33813614, "lava-cake"),
    "FOOD-DS-002": (6262168,  "kunafa"),
    "FOOD-DS-003": (754954,   "tiramisu"),
    "FOOD-DS-004": (633501,   "creme-brulee"),
    "FOOD-DS-005": (20595416, "umm-ali"),
    "FOOD-DS-006": (1105166,  "fruit-salad"),
    "FOOD-DS-007": (6419594,  "baklava"),
    "FOOD-DS-008": (14132776, "ice-cream"),
}

# Fallback images per category when primary fails
FALLBACKS = {
    "Starters":  [(1640777, "salad"), (2097090, "starter")],
    "Mains":     [(1640772, "main"),  (958545,  "food")],
    "Beverages": [(312418,  "drink"), (302899,  "beverage")],
    "Desserts":  [(291528,  "dessert"),(1352015, "sweet")],
}

def download_image(photo_id, slug, item_code):
    """Download from Pexels CDN. Returns local file path or None."""
    filename = f"{item_code.lower()}.jpg"
    dest = os.path.join(IMG_DIR, filename)
    if os.path.exists(dest) and os.path.getsize(dest) > 5000:
        return dest  # already downloaded

    url = (f"https://images.pexels.com/photos/{photo_id}/"
           f"pexels-photo-{photo_id}.jpeg"
           f"?auto=compress&cs=tinysrgb&w=400&h=300&fit=crop")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RestaurantPOS/1.0)",
        "Accept":     "image/jpeg,image/*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 5000:
            return None
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    except Exception as e:
        return None

print("\n=== DOWNLOADING FOOD IMAGES ===\n")

ok = 0
failed = []

for item_code, (photo_id, slug) in ITEM_IMAGES.items():
    if not frappe.db.exists("Item", item_code):
        continue

    local_path = download_image(photo_id, slug, item_code)

    if not local_path:
        # Try fallback based on item group
        ig = frappe.db.get_value("Item", item_code, "item_group")
        for fb_id, fb_slug in FALLBACKS.get(ig, []):
            local_path = download_image(fb_id, f"{item_code.lower()}-fb", item_code)
            if local_path:
                break

    if local_path:
        web_path = f"/files/pos_images/{os.path.basename(local_path)}"
        frappe.db.set_value("Item", item_code, "image", web_path)
        ok += 1
        print(f"  ✓ {item_code}: {web_path}")
    else:
        failed.append(item_code)
        print(f"  ✗ {item_code}: download failed")

frappe.db.commit()
print(f"\n✓ Images: {ok} downloaded and linked, {len(failed)} failed.")
if failed:
    print(f"  Failed: {failed}")
frappe.destroy()
