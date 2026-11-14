# currency_rates.py
"""
Dnevni kurs NBS za MicroStockApp (Standalone Edition).
- Čita NBS_API_KEY iz baze (app_settings) ako ga je kupac uneo.
- Ako kupac nema API ključ, koristi kurs iz baze ili podrazumevani fallback (EUR=117.20, USD=108.50)
  i omogućava kupcu da u svakom trenutku ručno upiše kurs.
"""

import os
import warnings
import requests
from datetime import date

from db_adapter import connect
from database import get_app_settings

_MEMORY_CACHE = {}
_API_CALLED_TODAY = None

NBS_API_URL = "https://allratestoday.com/api/v1/central-bank/nbs/latest"

DEFAULT_FALLBACK_RATES = {
    ("EUR", "RSD"): 117.20,
    ("USD", "RSD"): 108.50,
}

warnings.filterwarnings("ignore", message="Unable to find acceptable character detection dependency")


def _get_nbs_key() -> str:
    """Čita NBS API ključ koji je kupac uneo u podešavanjima aplikacije."""
    settings = get_app_settings()
    return (settings.get("nbs_api_key") or os.getenv("NBS_API_KEY") or "").strip()


def fetch_nbs_latest():
    """Povlači najnoviju NBS kursnu listu ako kupac ima unet API ključ."""
    api_key = _get_nbs_key()
    if not api_key:
        raise RuntimeError("NBS API ključ nije unet u podešavanjima (koristi se lokalni/ručni kurs).")

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(NBS_API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rates = []
    for r in data.get("rates", []):
        base = r.get("base")
        quote = r.get("quote")
        value = r.get("value")
        if base and quote and value is not None:
            rates.append({
                "source": base.upper(),
                "target": quote.upper(),
                "rate": float(value),
            })

    return {
        "rate_date": data.get("rate_date") or str(date.today()),
        "rates": rates,
    }


def get_rate(source, target):
    """
    Vraća kurs za par (npr. EUR -> RSD).
    Redosled: memorija -> baza (danas) -> API (ako kupac ima ključ) -> baza (stariji) -> podrazumevani kurs.
    """
    global _API_CALLED_TODAY
    source = source.upper()
    target = target.upper()
    today_str = str(date.today())

    if source == target:
        return {"rate": 1.0, "rate_date": today_str, "source": source, "target": target}

    cache_key = f"{source}_{target}"

    # 1) Memorija
    mem = _MEMORY_CACHE.get(cache_key)
    if mem and mem.get("date") == today_str:
        return {
            "rate": mem["rate"],
            "rate_date": today_str,
            "source": source,
            "target": target,
            "from_memory": True,
        }

    # 2) Baza — današnji kurs
    cached = get_cached_rate(source, target, today_only=True)
    if cached:
        _MEMORY_CACHE[cache_key] = {"rate": cached["rate"], "date": today_str}
        return cached

    # 3) API — samo ako je kupac uneo svoj NBS ključ i ako već nije pozvan danas
    if _API_CALLED_TODAY != today_str and _get_nbs_key():
        try:
            result = fetch_nbs_latest()
            _API_CALLED_TODAY = today_str
            try:
                save_rates_to_db(result)
            except Exception as e:
                print(f"[currency_rates] save greška: {e}")

            for r in result["rates"]:
                if r["source"] == source and r["target"] == target:
                    _MEMORY_CACHE[cache_key] = {"rate": r["rate"], "date": today_str}
                    return {
                        "rate": r["rate"],
                        "rate_date": result["rate_date"],
                        "source": source,
                        "target": target,
                    }
        except Exception as e:
            print(f"[currency_rates] NBS API info: {e}")
            _API_CALLED_TODAY = today_str

    # 4) Fallback — najnoviji kurs iz baze (ručno unet ili od prethodnih dana)
    cached = get_cached_rate(source, target, today_only=False)
    if cached:
        _MEMORY_CACHE[cache_key] = {"rate": cached["rate"], "date": today_str}
        return cached

    # 5) Bezbedan podrazumevani kurs (npr. 117.20 za EUR->RSD umesto 1.0)
    fallback_val = DEFAULT_FALLBACK_RATES.get((source, target), 1.0)
    _MEMORY_CACHE[cache_key] = {"rate": fallback_val, "date": today_str}
    return {
        "rate": fallback_val,
        "rate_date": today_str,
        "source": source,
        "target": target,
        "fallback": True,
    }


def save_rates_to_db(rates_data):
    """Upisuje kursnu listu u exchange_rates (UPSERT)."""
    rate_date = rates_data.get("rate_date") or str(date.today())
    conn = connect()
    inserted = 0
    try:
        for r in rates_data["rates"]:
            conn.execute("""
                INSERT INTO exchange_rates (source_currency, target_currency, rate, rate_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(source_currency, target_currency, rate_date)
                DO UPDATE SET
                    rate = excluded.rate,
                    fetched_at = CURRENT_TIMESTAMP
            """, (r["source"], r["target"], r["rate"], rate_date))
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_cached_rate(source, target, today_only=False):
    source = source.upper()
    target = target.upper()

    conn = connect()
    try:
        if today_only:
            row = conn.execute("""
                SELECT source_currency, target_currency, rate, rate_date
                FROM exchange_rates
                WHERE source_currency = %s AND target_currency = %s
                  AND rate_date::text = CURRENT_DATE::text
                ORDER BY rate_date DESC
                LIMIT 1
            """, (source, target)).fetchone()
        else:
            row = conn.execute("""
                SELECT source_currency, target_currency, rate, rate_date
                FROM exchange_rates
                WHERE source_currency = %s AND target_currency = %s
                ORDER BY rate_date DESC
                LIMIT 1
            """, (source, target)).fetchone()
    finally:
        conn.close()

    if row:
        return {
            "rate": float(row["rate"]),
            "rate_date": row["rate_date"],
            "source": row["source_currency"],
            "target": row["target_currency"],
            "cached": True,
        }
    return None


def list_all_rates():
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT DISTINCT ON (source_currency, target_currency)
                source_currency, target_currency, rate, rate_date, fetched_at
            FROM exchange_rates
            ORDER BY source_currency, target_currency, rate_date DESC
        """).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        fetched = r["fetched_at"]
        if fetched and hasattr(fetched, "strftime"):
            fetched = fetched.strftime("%d.%m.%Y %H:%M")
        elif fetched:
            fetched = str(fetched)

        rate_date = r["rate_date"]
        if rate_date and hasattr(rate_date, "strftime"):
            rate_date = rate_date.strftime("%d.%m.%Y")
        elif rate_date:
            rate_date = str(rate_date)

        result.append({
            "source": r["source_currency"],
            "target": r["target_currency"],
            "rate": float(r["rate"]),
            "rate_date": rate_date,
            "fetched_at": fetched,
        })
    return result


def set_manual_rate(source, target, rate, rate_date=None):
    source = source.upper().strip()
    target = target.upper().strip()
    if rate_date is None:
        rate_date = date.today()

    conn = connect()
    try:
        conn.execute("""
            INSERT INTO exchange_rates
                (source_currency, target_currency, rate, rate_date)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_currency, target_currency, rate_date)
            DO UPDATE SET
                rate = excluded.rate,
                fetched_at = CURRENT_TIMESTAMP
        """, (source, target, float(rate), rate_date))
        conn.commit()
        _MEMORY_CACHE.pop(f"{source}_{target}", None)
    finally:
        conn.close()


def refresh_from_nbs():
    try:
        data = fetch_nbs_latest()
        n = save_rates_to_db(data)
        _MEMORY_CACHE.clear()
        return True, n, f"Uspešno povučeno {n} kurseva za {data['rate_date']}."
    except Exception as e:
        return False, 0, f"Info: {e}"