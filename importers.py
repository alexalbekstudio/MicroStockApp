# importers.py
"""
CSV import iz raznih platformi.
Podržava: Etsy, Gumroad, Payhip, Shopify, TikTok Shop, Instagram, generički CSV.
Automatski prepoznaje kolone čak i ako korisnik izabere pogrešan preset.
"""
import csv
import io
import json
from datetime import datetime

from db_adapter import connect
from i18n import get_locale


# Univerzalni fallback kandidati (ako izabrani preset ne nađe kolonu u CSV-u)
UNIVERSAL_CANDIDATES = {
    "customer_name": [
        "Buyer Name", "Buyer", "Ship Name", "Billing Name", "Customer",
        "Customer Name", "Customer Email", "Buyer Email", "Email",
        "Buyer Username", "Recipient", "Full Name", "Name",
        "customer_name", "customer", "kupac", "ime", "klijent"
    ],
    "external_id": [
        "Order ID", "Order Number", "Name", "Id", "ID", "Sale ID",
        "Transaction ID", "Reference", "external_id", "order_id", "broj_narudzbine"
    ],
    "order_date": [
        "Order Date", "Sale Date", "Date", "Created", "Purchase Date",
        "Created at", "Paid at", "Created Time", "Order Time", "Paid Time",
        "order_date", "created_at", "datum"
    ],
    "status": [
        "Status", "Order Status", "State", "Payment Status",
        "Financial Status", "Fulfillment Status", "status"
    ],
    "note": [
        "Note from Buyer", "Notes", "Message", "Note", "Buyer Message",
        "note", "notes", "napomena"
    ],
    "items.sku": [
        "SKU", "Product SKU", "Product ID", "Permalink", "Lineitem sku",
        "Seller SKU", "sku", "sifra", "šifra", "code"
    ],
    "items.name": [
        "Item Name", "Product Name", "Title", "Product", "Item",
        "Lineitem name", "product_name", "name", "naziv", "artikal"
    ],
    "items.qty": [
        "Quantity", "Qty", "Lineitem quantity", "quantity", "qty",
        "kolicina", "količina", "kom", "stock", "stanje"
    ],
    "items.unit_price": [
        "Price", "Item Price", "Unit Price", "Amount", "Total",
        "Lineitem price", "SKU Unit Original Price",
        "unit_price", "price", "cena", "cijena", "cost"
    ],
}

PRESETS = {
    "etsy": {
        "label": "Etsy (Orders.csv)",
        "customer_name": ["Buyer Name", "Buyer", "Ship Name"],
        "external_id":   ["Order ID", "Order Number"],
        "order_date":    ["Order Date", "Sale Date", "Date"],
        "status":        ["Status", "Order Status"],
        "channel":       "Etsy",
        "items": {
            "sku":        ["SKU", "Product SKU"],
            "name":       ["Item Name", "Product Name", "Title"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Item Price", "Unit Price"],
        },
        "note":          ["Note from Buyer", "Notes", "Message"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "gumroad": {
        "label": "Gumroad (Sales.csv)",
        "customer_name": ["Buyer Email", "Email", "Customer"],
        "external_id":   ["Order Number", "ID", "Sale ID"],
        "order_date":    ["Created", "Date", "Purchase Date"],
        "status":        ["Status", "State"],
        "channel":       "Gumroad",
        "items": {
            "sku":        ["Product ID", "SKU", "Permalink"],
            "name":       ["Product Name", "Product"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Amount", "Total"],
        },
        "note":          ["Notes", "Note"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "payhip": {
        "label": "Payhip (Sales.csv)",
        "customer_name": ["Customer Email", "Buyer Email", "Name"],
        "external_id":   ["Order ID", "Transaction ID", "ID"],
        "order_date":    ["Date", "Created"],
        "status":        ["Status", "Payment Status"],
        "channel":       "Payhip",
        "items": {
            "sku":        ["Product ID", "SKU"],
            "name":       ["Product Name", "Item"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Amount"],
        },
        "note":          ["Notes"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "shopify": {
        "label": "Shopify (orders_export.csv)",
        "customer_name": ["Billing Name", "Customer", "Shipping Name"],
        "external_id":   ["Name", "Order ID", "Id"],
        "order_date":    ["Created at", "Paid at", "Date"],
        "status":        ["Financial Status", "Fulfillment Status"],
        "channel":       "Shopify",
        "items": {
            "sku":        ["Lineitem sku", "SKU"],
            "name":       ["Lineitem name", "Product"],
            "qty":        ["Lineitem quantity", "Qty"],
            "unit_price": ["Lineitem price", "Price"],
        },
        "note":          ["Notes", "Note"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "tiktok": {
        "label": "TikTok Shop (OrderSKUList.csv)",
        "customer_name": ["Buyer Username", "Customer Name", "Recipient"],
        "external_id":   ["Order ID", "Order Number"],
        "order_date":    ["Created Time", "Order Time", "Paid Time"],
        "status":        ["Order Status", "Status"],
        "channel":       "TikTok",
        "items": {
            "sku":        ["Seller SKU", "SKU"],
            "name":       ["Product Name", "Item Name"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["SKU Unit Original Price", "Unit Price", "Price"],
        },
        "note":          ["Buyer Message", "Notes"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "instagram": {
        "label": "Instagram / Meta (generic)",
        "customer_name": ["Customer", "Buyer", "Name", "Full Name"],
        "external_id":   ["Order ID", "ID", "Reference"],
        "order_date":    ["Date", "Created", "Order Date"],
        "status":        ["Status"],
        "channel":       "Instagram",
        "items": {
            "sku":        ["SKU"],
            "name":       ["Product", "Item", "Product Name"],
            "qty":        ["Qty", "Quantity"],
            "unit_price": ["Price", "Unit Price"],
        },
        "note":          ["Note", "Notes"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
    "generic": {
        "label": "Generic CSV (Auto / Manual mapping)",
        "customer_name": ["customer", "customer_name", "buyer", "name"],
        "external_id":   ["external_id", "order_id", "id"],
        "order_date":    ["date", "order_date", "created_at"],
        "status":        ["status"],
        "channel":       None,
        "items": {
            "sku":        ["sku"],
            "name":       ["product", "product_name", "item", "name"],
            "qty":        ["qty", "quantity"],
            "unit_price": ["price", "unit_price", "amount"],
        },
        "note":          ["note", "notes"],
        "customer_phone": ["Billing Phone", "Shipping Phone", "Phone"],
    },
}


# ==================== PARSIRANJE ====================

def detect_delimiter(sample: str) -> str:
    """Detektuje , ili ; ili \\t."""
    for d in [",", ";", "\t"]:
        if sample.count(d) > sample.count(","):
            return d
    return ","


def read_csv(file_bytes: bytes, delimiter=None):
    """Vraća (fieldnames, rows) — lista dict-ova."""
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Cannot decode CSV file / Ne mogu da dekodiram CSV.")

    if delimiter is None:
        delimiter = detect_delimiter(text[:1000])

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    clean_fields = [f.strip() for f in (reader.fieldnames or []) if f]
    rows = []
    for r in reader:
        rows.append({(k.strip() if k else ""): v for k, v in r.items()})
    return clean_fields, rows


def find_column(fieldnames, candidates):
    """Vraća prvo ime kolone iz `candidates` koje postoji u fieldnames (case-insensitive)."""
    if not candidates:
        return None
    if isinstance(candidates, str):
        candidates = [candidates]
    lower_map = {f.lower().strip(): f for f in fieldnames if f}
    for c in candidates:
        key = c.lower().strip()
        if key in lower_map:
            return lower_map[key]
    return None


def build_mapping(preset_key, fieldnames, overrides=None):
    """
    Automatski mapira kolone iz CSV-a:
    1. Ručni izbor korisnika (overrides)
    2. Kandidati iz izabranog preseta
    3. Univerzalni fallback kandidati (ako je izabran pogrešan preset)
    """
    preset = PRESETS.get(preset_key, PRESETS["generic"])
    mapping = {}

    def pick_top(field):
        if overrides and overrides.get(field):
            return overrides[field]
        found = find_column(fieldnames, preset.get(field))
        if not found:
            found = find_column(fieldnames, UNIVERSAL_CANDIDATES.get(field, []))
        return found

    mapping["customer_name"] = pick_top("customer_name")
    mapping["external_id"]   = pick_top("external_id")
    mapping["order_date"]    = pick_top("order_date")
    mapping["status"]        = pick_top("status")
    mapping["note"]          = pick_top("note")

    items_map = {}
    for sub in ("sku", "name", "qty", "unit_price"):
        ov_key = f"items.{sub}"
        if overrides and overrides.get(ov_key):
            items_map[sub] = overrides[ov_key]
        else:
            found = find_column(fieldnames, preset["items"].get(sub))
            if not found:
                found = find_column(fieldnames, UNIVERSAL_CANDIDATES.get(ov_key, []))
            items_map[sub] = found

    mapping["items"] = items_map
    mapping["channel"] = preset.get("channel")
    return mapping


# ==================== VALIDACIJA (Dvojezična SR/EN) ====================

def validate_mapping(mapping):
    """Vraća listu grešaka na jeziku korisnika (SR ili EN)."""
    is_en = (get_locale() == "en")
    errors = []
    if not mapping.get("customer_name"):
        errors.append(
            "Missing column mapping for: Customer Name (customer_name)"
            if is_en else "Nedostaje mapiranje za: Ime kupca (customer_name)"
        )
    if not mapping["items"].get("qty"):
        errors.append(
            "Missing column mapping for: Quantity (items.qty)"
            if is_en else "Nedostaje mapiranje za: Količina (items.qty)"
        )
    if not mapping["items"].get("unit_price"):
        errors.append(
            "Missing column mapping for: Price (items.unit_price)"
            if is_en else "Nedostaje mapiranje za: Cena (items.unit_price)"
        )
    if not (mapping["items"].get("sku") or mapping["items"].get("name")):
        errors.append(
            "At least one is required: SKU or Product Name"
            if is_en else "Treba bar jedno: SKU ili Naziv proizvoda"
        )
    return errors


# ==================== IMPORT ====================

def import_rows(rows, mapping, channel_id, source_name,
                auto_create_products=True, user_id=None,
                filename=""):
    """
    Uvozi redove. Vraća dict sa rezultatima.
    """
    uid = user_id or 1

    grouped = {}
    ungrouped = []
    for i, row in enumerate(rows):
        ext = _get(row, mapping.get("external_id"))
        if ext:
            grouped.setdefault(str(ext).strip(), []).append((i, row))
        else:
            ungrouped.append((i, row))

    results = {
        "imported": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "created_orders": [],
        "created_products": [],
    }

    conn = connect()

    # 1) Grupisane
    for ext_id, group in grouped.items():
        try:
            _import_group(conn, ext_id, group, mapping, channel_id, source_name,
                          auto_create_products, results, user_id=uid)
            conn.commit()
        except Exception as e:
            conn.rollback()
            results["failed"] += 1
            results["errors"].append(f"external_id={ext_id}: {e}")

    # 2) Negrupisane (bez external_id) — svaki red zasebno
    for i, row in ungrouped:
        try:
            _import_group(conn, None, [(i, row)], mapping, channel_id, source_name,
                          auto_create_products, results, user_id=uid)
            conn.commit()
        except Exception as e:
            conn.rollback()
            results["failed"] += 1
            results["errors"].append(f"red {i+2}: {e}")

    # Log
    try:
        conn.execute("""
            INSERT INTO import_logs
            (user_id, source, filename, rows_total, rows_imported,
             rows_skipped, rows_failed, errors)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (uid, source_name, filename, len(rows),
              results["imported"], results["skipped"], results["failed"],
              json.dumps(results["errors"][:50], ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        results["errors"].append(f"Log greška: {e}")
    finally:
        conn.close()

    return results


def _import_group(conn, ext_id, group, mapping, channel_id, source_name,
                  auto_create_products, results, user_id=1):
    """Uvozi jednu narudžbinu (može imati više stavki)."""
    from models import create_order_tx

    # Duplikat — preko iste konekcije za datog korisnika
    if ext_id:
        existing = conn.execute(
            "SELECT id FROM orders WHERE external_id=%s AND source=%s AND user_id=%s",
            (str(ext_id), str(source_name), user_id)
        ).fetchone()
        if existing:
            results["skipped"] += 1
            return

    first_row = group[0][1]
    customer = _get(first_row, mapping.get("customer_name")) or "Nepoznat kupac"
    note = _get(first_row, mapping.get("note")) or ""

    items = []
    for _, row in group:
        item = _build_item(conn, row, mapping, auto_create_products, results, user_id=user_id)
        if item:
            items.append(item)

    if not items:
        results["skipped"] += 1
        return

    order_id, dup = create_order_tx(
        conn,
        user_id=user_id,
        customer_name=str(customer).strip(),
        channel_id=channel_id,
        items=items,
        note=str(note).strip(),
        external_id=ext_id,
        source=source_name,
    )
    if dup:
        results["skipped"] += 1
    else:
        results["imported"] += 1
        results["created_orders"].append(order_id)


def _build_item(conn, row, mapping, auto_create_products, results, user_id=1):
    """Vraća {product_id, qty} ili None. Koristi prosleđenu konekciju."""
    sku = _get(row, mapping["items"].get("sku"))
    name = _get(row, mapping["items"].get("name"))
    qty_raw = _get(row, mapping["items"].get("qty"))
    price_raw = _get(row, mapping["items"].get("unit_price"))

    if not qty_raw:
        return None
    try:
        qty = int(float(str(qty_raw).replace(",", ".")))
    except (ValueError, TypeError):
        return None
    if qty <= 0:
        return None

    price = None
    if price_raw not in (None, ""):
        try:
            price = float(str(price_raw).replace(",", ".").replace("€", "").replace("$", "").strip())
        except (ValueError, TypeError):
            price = None

    # Nađi proizvod po SKU, pa po imenu (za trenutnog korisnika)
    product_id = None
    if sku:
        row_db = conn.execute(
            "SELECT id FROM products WHERE sku=%s AND user_id=%s",
            (str(sku).strip(), user_id)
        ).fetchone()
        if row_db:
            product_id = row_db["id"]
    if not product_id and name:
        row_db = conn.execute(
            "SELECT id FROM products WHERE name=%s AND user_id=%s",
            (str(name).strip(), user_id)
        ).fetchone()
        if row_db:
            product_id = row_db["id"]

    # Ako nema — kreiraj sa user_id
    if not product_id and auto_create_products:
        new_sku = str(sku).strip() if sku else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        new_name = str(name).strip() if name else f"Proizvod {new_sku}"
        cur = conn.execute("""
            INSERT INTO products (user_id, sku, name, price, cost, stock, low_stock_at)
            VALUES (%s, %s, %s, %s, 0, 0, 3)
            RETURNING id
        """, (user_id, new_sku, new_name, price or 0))
        row_new = cur.fetchone()
        product_id = row_new["id"] if row_new else None
        if product_id:
            results["created_products"].append(new_sku)

    if not product_id:
        return None

    return {"product_id": product_id, "qty": qty}


def _get(row, key):
    """Bezbedno čitanje iz dict-a, case-insensitive fallback."""
    if not key:
        return None
    if key in row:
        return row[key]
    key_l = key.lower().strip()
    for k, v in row.items():
        if k and k.lower().strip() == key_l:
            return v
    return None