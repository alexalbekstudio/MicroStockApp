# database.py
"""
Inicijalizacija baze + auto-migracije + globalna podešavanja (app_settings) za Standalone verziju.
"""
import os
from pathlib import Path
from db_adapter import connect

SCHEMA = Path(__file__).parent / "schema.sql"


def init_db():
    """Kreira tabele ako ne postoje (idempotentno) + auto-migracije."""
    conn = connect()

    # 0) OSIGURAJ TABELU USERS I OSNOVNE TABELE PRE SCHEMA.SQL (sprečava greške pri prvom startu)
    pre_schema = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            name            TEXT,
            role            TEXT NOT NULL DEFAULT 'admin',
            active          INTEGER NOT NULL DEFAULT 1,
            language        TEXT DEFAULT 'sr',
            currency        TEXT DEFAULT 'RSD',
            capital         NUMERIC(12,2) NOT NULL DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login      TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS channels (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            fee_percent NUMERIC(5,2) NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id              SERIAL PRIMARY KEY,
            source_currency TEXT NOT NULL,
            target_currency TEXT NOT NULL,
            rate            NUMERIC(12,4) NOT NULL,
            rate_date       DATE NOT NULL DEFAULT CURRENT_DATE,
            fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_exchange_rate UNIQUE(source_currency, target_currency, rate_date)
        )
        """
    ]
    for stmt in pre_schema:
        try:
            conn.execute(stmt.strip())
            conn.commit()
        except Exception:
            conn.rollback()

    # 1) IZVRŠI SCHEMA.SQL
    if SCHEMA.exists():
        with open(SCHEMA, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        for stmt in _split_sql(schema_sql):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception as e:
                conn.rollback()
                msg = str(e).lower()
                if "already exists" not in msg and "duplicate" not in msg:
                    print(f"⚠️  Preskočeno: {stmt[:60]}... ({e})")

    # 2) AUTO-MIGRACIJE + APP_SETTINGS TABELA
    _run_migrations(conn)

    conn.close()
    print("✅ Baza inicijalizovana (Standalone Mode)")


def _run_migrations(conn):
    """
    Male izmene šeme koje se izvršavaju pri svakom startu.
    Sve koristi IF NOT EXISTS — bezbedno za ponovno pokretanje.
    """
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'sr'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'RSD'",
        # 1) users.capital (kapital vlasnika)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS capital NUMERIC(12,2) NOT NULL DEFAULT 0",

        # 2) capital_transactions (istorija uplata/isplata)
        """
        CREATE TABLE IF NOT EXISTS capital_transactions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            type        TEXT NOT NULL,
            amount      NUMERIC(12,2) NOT NULL,
            balance     NUMERIC(12,2) NOT NULL,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3) Index za capital_transactions
        """
        CREATE INDEX IF NOT EXISTS idx_capital_tx_user
        ON capital_transactions(user_id, created_at DESC)
        """,

        # 4) Novi kanali (Shopify, Gumroad, Payhip, TikTok)
        """
        INSERT INTO channels (name, fee_percent) VALUES
            ('Shopify', 0.0),
            ('Gumroad', 0.0),
            ('Payhip',  0.0),
            ('TikTok',  0.0)
        ON CONFLICT (name) DO NOTHING
        """,

        # 5) password_resets (zaboravljena šifra)
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token       TEXT NOT NULL UNIQUE,
            expires_at  TIMESTAMP NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 6) Index za password_resets
        """
        CREATE INDEX IF NOT EXISTS idx_password_resets_token
        ON password_resets(token)
        """,

        # 8) suppliers — dobavljači
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id                SERIAL PRIMARY KEY,
            name              TEXT NOT NULL,
            contact_person    TEXT,
            email             TEXT,
            phone             TEXT,
            address           TEXT,
            city              TEXT,
            tax_id            TEXT,
            iban              TEXT,
            swift             TEXT,
            product_categories TEXT,
            notes             TEXT,
            active            INTEGER NOT NULL DEFAULT 1,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 10) purchase_invoices — računi nabavke
        """
        CREATE TABLE IF NOT EXISTS purchase_invoices (
            id              SERIAL PRIMARY KEY,
            supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            invoice_number  TEXT,
            invoice_date    DATE,
            due_date        DATE,
            paid_date       DATE,
            amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL DEFAULT 'RSD',
            status          TEXT NOT NULL DEFAULT 'pending',
            file_data       BYTEA,
            file_name       TEXT,
            file_mime       TEXT,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 11) Index za pretragu računa
        """
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_supplier
        ON purchase_invoices(supplier_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_status
        ON purchase_invoices(status)
        """,

        # 12) purchase_items — stavke računa
        """
        CREATE TABLE IF NOT EXISTS purchase_items (
            id                  SERIAL PRIMARY KEY,
            purchase_invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
            product_id          INTEGER REFERENCES products(id) ON DELETE SET NULL,
            description         TEXT,
            qty                 NUMERIC(12,2) NOT NULL DEFAULT 0,
            unit_cost           NUMERIC(12,2) NOT NULL DEFAULT 0,
            total               NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_items_invoice
        ON purchase_items(purchase_invoice_id)
        """,

        # 9) Index za pretragu dobavljača
        """
        CREATE INDEX IF NOT EXISTS idx_suppliers_name
        ON suppliers(name)
        """,

        # 13) orders.customer_phone — za WhatsApp deep links
        """
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_phone TEXT
        """,

        # 14) MULTI-TENANCY: products.user_id
        """
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """,
        """
        UPDATE products SET user_id = 1 WHERE user_id IS NULL
        """,

        # 15) MULTI-TENANCY: orders.user_id
        """
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """,
        """
        UPDATE orders SET user_id = 1 WHERE user_id IS NULL
        """,

        # 16) MULTI-TENANCY: suppliers.user_id
        """
        ALTER TABLE suppliers
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """,
        """
        UPDATE suppliers SET user_id = 1 WHERE user_id IS NULL
        """,

        # 17) MULTI-TENANCY: purchase_invoices.user_id
        """
        ALTER TABLE purchase_invoices
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """,
        """
        UPDATE purchase_invoices SET user_id = 1 WHERE user_id IS NULL
        """,

        # 18) MULTI-TENANCY: projects.user_id
        """
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """,
        """
        UPDATE projects SET user_id = 1 WHERE user_id IS NULL
        """,

        # 19) business_expenses — operativni i fiksni režijski troškovi biznisa
        """
        CREATE TABLE IF NOT EXISTS business_expenses (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            category    TEXT NOT NULL DEFAULT 'Ostalo',
            amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
            expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_business_expenses_user_date
        ON business_expenses(user_id, expense_date DESC)
        """,

        # 20) Oznaka za repromaterijal / sirovinu i mernu jedinicu u tabeli products
        """
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS is_material INTEGER NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT 'kom'
        """,

        # 21) product_recipes — tabela koja definise sastavnicu (BOM)
        """
        CREATE TABLE IF NOT EXISTS product_recipes (
            id                  SERIAL PRIMARY KEY,
            parent_product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            material_product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            qty_needed          NUMERIC(12,4) NOT NULL DEFAULT 1,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_parent_material UNIQUE(parent_product_id, material_product_id)
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_recipes_parent
        ON product_recipes(parent_product_id)
        """,

        # 22) STANDALONE PODESAVANJA KUPCA (app_settings)
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            id                  INTEGER PRIMARY KEY DEFAULT 1,
            company_name        TEXT DEFAULT 'Moja Firma',
            company_pib         TEXT DEFAULT '',
            company_mb          TEXT DEFAULT '',
            company_address     TEXT DEFAULT '',
            company_bank_acc    TEXT DEFAULT '',
            company_iban        TEXT DEFAULT '',
            company_swift       TEXT DEFAULT '',
            currency_base       TEXT DEFAULT 'RSD',
            nbs_api_key         TEXT DEFAULT '',
            smtp_server         TEXT DEFAULT 'smtp.gmail.com',
            smtp_port           INTEGER DEFAULT 587,
            smtp_use_tls        INTEGER DEFAULT 1,
            smtp_username       TEXT DEFAULT '',
            smtp_password       TEXT DEFAULT '',
            alert_email         TEXT DEFAULT '',
            report_email        TEXT DEFAULT '',
            pending_order_days  INTEGER DEFAULT 3,
            license_tier        TEXT DEFAULT 'ultimate',
            license_key         TEXT DEFAULT '',
            addon_analytics     INTEGER DEFAULT 0,
            addon_suppliers     INTEGER DEFAULT 0,
            addon_projects      INTEGER DEFAULT 0,
            addon_recipes       INTEGER DEFAULT 0,
            is_configured       INTEGER DEFAULT 0,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT single_row CHECK (id = 1)
        )
        """,

        # Osiguraj podrazumevani red u app_settings
        """
        INSERT INTO app_settings (id, company_name, license_tier)
        VALUES (1, 'Moja Firma', 'ultimate')
        ON CONFLICT (id) DO NOTHING
        """,

        # Osiguraj osnovne početne kurseve ako kupac nema NBS API ključ
        """
        INSERT INTO exchange_rates (source_currency, target_currency, rate, rate_date)
        VALUES
            ('EUR', 'RSD', 117.20, CURRENT_DATE),
            ('USD', 'RSD', 108.50, CURRENT_DATE)
        ON CONFLICT (source_currency, target_currency, rate_date) DO NOTHING
        """
    ]

    for sql in migrations:
        try:
            conn.execute(sql.strip())
            conn.commit()
        except Exception as e:
            conn.rollback()
            msg = str(e).lower()
            if "already exists" not in msg and "duplicate" not in msg:
                print(f"⚠️  Migracija preskočena: {sql[:60]}... ({e})")

    print("✅ Auto-migracije završene")


# ============================================================
# HELPERI ZA ČITANJE I UPIS PODEŠAVANJA KUPCA
# ============================================================

def get_app_settings() -> dict:
    """Vraća sva podešavanja aplikacije iz baze (sa fallback-om na .env ako zatreba)."""
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "company_name": "Moja Firma",
        "company_pib": "",
        "company_mb": "",
        "company_address": "",
        "company_bank_acc": "",
        "company_iban": "",
        "company_swift": "",
        "currency_base": os.getenv("CURRENCY_BASE", "RSD"),
        "nbs_api_key": os.getenv("NBS_API_KEY", ""),
        "smtp_server": os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("MAIL_PORT", "587")),
        "smtp_use_tls": 1,
        "smtp_username": os.getenv("MAIL_USERNAME", ""),
        "smtp_password": os.getenv("MAIL_PASSWORD", ""),
        "alert_email": os.getenv("ALERT_EMAIL", ""),
        "report_email": os.getenv("REPORT_EMAIL", ""),
        "pending_order_days": int(os.getenv("PENDING_ORDER_DAYS", "3")),
        "license_tier": os.getenv("LICENSE_TIER", "ultimate"),
        "license_key": "",
        "addon_analytics": 0,
        "addon_suppliers": 0,
        "addon_projects": 0,
        "addon_recipes": 0,
        "is_configured": 0,
    }


def save_app_settings(data: dict) -> bool:
    """Čuva podešavanja koja je kupac uneo na Settings stranici."""
    conn = connect()
    try:
        conn.execute("""
            UPDATE app_settings SET
                company_name       = %s,
                company_pib        = %s,
                company_mb         = %s,
                company_address    = %s,
                company_bank_acc   = %s,
                company_iban       = %s,
                company_swift      = %s,
                currency_base      = %s,
                nbs_api_key        = %s,
                smtp_server        = %s,
                smtp_port          = %s,
                smtp_use_tls       = %s,
                smtp_username      = %s,
                smtp_password      = %s,
                alert_email        = %s,
                report_email       = %s,
                pending_order_days = %s,
                license_tier       = %s,
                license_key        = %s,
                addon_analytics    = %s,
                addon_suppliers    = %s,
                addon_projects     = %s,
                addon_recipes      = %s,
                is_configured      = 1,
                updated_at         = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (
            data.get("company_name", "Moja Firma"),
            data.get("company_pib", ""),
            data.get("company_mb", ""),
            data.get("company_address", ""),
            data.get("company_bank_acc", ""),
            data.get("company_iban", ""),
            data.get("company_swift", ""),
            data.get("currency_base", "RSD"),
            data.get("nbs_api_key", ""),
            data.get("smtp_server", "smtp.gmail.com"),
            int(data.get("smtp_port") or 587),
            1 if data.get("smtp_use_tls", True) else 0,
            data.get("smtp_username", ""),
            data.get("smtp_password", ""),
            data.get("alert_email", ""),
            data.get("report_email", ""),
            int(data.get("pending_order_days") or 3),
            data.get("license_tier", "ultimate"),
            data.get("license_key", ""),
            int(data.get("addon_analytics") or 0),
            int(data.get("addon_suppliers") or 0),
            int(data.get("addon_projects") or 0),
            int(data.get("addon_recipes") or 0),
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[save_app_settings] Greška: {e}")
        return False
    finally:
        conn.close()


def _split_sql(sql):
    """Deli SQL po ; (prosto)."""
    parts = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(current))
            current = []
    if current:
        parts.append("\n".join(current))
    return parts


from db_adapter import get_conn  # noqa: F401

if __name__ == "__main__":
    init_db()