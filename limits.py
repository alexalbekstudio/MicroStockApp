# limits.py
"""
Upravljanje paketima i modulima za Standalone (One-Time Purchase) verziju.
Podržava 3 osnovna paketa (Core, Pro, Ultimate) + pojedinačne doplate za module (Add-ons).
"""
from db_adapter import connect
from database import get_app_settings

# Pravila za jednokratne pakete (zadržani i stari ključevi radi 100% kompatibilnosti sa template-ima)
PLANS = {
    "core": {
        "label": "Core (Osnovni)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": 1,
        "has_analytics": False,
        "has_suppliers": False,
        "has_projects": False,
        "has_recipes": False,
    },
    "pro": {
        "label": "Pro (Poslovni)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": 5,
        "has_analytics": True,
        "has_suppliers": True,
        "has_projects": False,
        "has_recipes": True,
    },
    "ultimate": {
        "label": "Ultimate (Komplet)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": float("inf"),
        "has_analytics": True,
        "has_suppliers": True,
        "has_projects": True,
        "has_recipes": True,
    },
    # Alias mapiranje za stari kod ako negde traži 'starter', 'business' ili 'trial'
    "starter": {
        "label": "Core (Osnovni)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": 1,
        "has_analytics": False,
        "has_suppliers": False,
        "has_projects": False,
        "has_recipes": False,
    },
    "business": {
        "label": "Ultimate (Komplet)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": float("inf"),
        "has_analytics": True,
        "has_suppliers": True,
        "has_projects": True,
        "has_recipes": True,
    },
    "trial": {
        "label": "Ultimate (Demo)",
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": float("inf"),
        "has_analytics": True,
        "has_suppliers": True,
        "has_projects": True,
        "has_recipes": True,
    }
}


def get_user_plan_context(user_id=None):
    """
    U Standalone verziji licenca je trajna (is_active = True) i čita se iz app_settings.
    Takođe proverava pojedinačno dokupljene dodatke (add-ons).
    """
    settings = get_app_settings()
    tier = (settings.get("license_tier") or "ultimate").lower()

    base_rules = dict(PLANS.get(tier, PLANS["ultimate"]))

    # Ako je kupac na Core ili Pro paketu, a dokupio je pojedinačni modul (+25€ / +30€):
    if settings.get("addon_analytics"):
        base_rules["has_analytics"] = True
    if settings.get("addon_suppliers"):
        base_rules["has_suppliers"] = True
    if settings.get("addon_projects"):
        base_rules["has_projects"] = True
    if settings.get("addon_recipes"):
        base_rules["has_recipes"] = True

    return tier, True, base_rules


def can_add_product(user_id):
    """U Standalone verziji broj proizvoda nije ograničen."""
    plan, is_active, rules = get_user_plan_context(user_id)
    if rules["max_products"] == float("inf"):
        return True, None

    conn = connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM products WHERE user_id = %s AND active = 1",
            (user_id,)
        ).fetchone()
        current_count = row["total"] if row else 0
    finally:
        conn.close()

    if current_count >= rules["max_products"]:
        return False, f"Dostigli ste limit od {rules['max_products']} proizvoda za paket '{plan.upper()}'."

    return True, None


def can_add_order(user_id):
    """U Standalone verziji broj porudžbina nije ograničen."""
    plan, is_active, rules = get_user_plan_context(user_id)
    if rules["max_orders_per_month"] == float("inf"):
        return True, None

    conn = connect()
    try:
        row = conn.execute("""
            SELECT COUNT(*) AS total FROM orders 
            WHERE user_id = %s 
              AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
        """, (user_id,)).fetchone()
        current_orders = row["total"] if row else 0
    finally:
        conn.close()

    if current_orders >= rules["max_orders_per_month"]:
        return False, f"Dostigli ste mesečni limit od {rules['max_orders_per_month']} narudžbina."

    return True, None