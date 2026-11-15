# pdf.py
"""
Generator PDF faktura i nalepnica koristeći fpdf2 sa Unicode fontom (DejaVuSans).
- Bez hardkodovanog ALEXANDAR logotipa (koristi logo kupca ako je otpremljen, ili samo naziv firme).
- Ispravljen RGB format QR koda (sprečava kose crte / distorziju u PDF-u).
- Popravljen položaj linije zaglavlja.
"""

import io
import re
import qrcode
import sys
from pathlib import Path
from datetime import datetime
from fpdf import FPDF

from database import get_app_settings

# --- Putanje do fontova ---
FONT_DIR = Path(__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

# --- Opcioni logo kupca (uploadovan kroz Settings) ---
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent
CUSTOM_LOGO_PATH = _APP_DIR / "company-logo.png"

# --- Boje ---
CRNA = (17, 17, 17)
SIVA = (120, 120, 120)
SVETLO_SIVA = (240, 240, 240)
ZELENA = (39, 174, 96)
CRVENA = (217, 83, 79)


def _format_nbs_account(acc_raw: str) -> str:
    """Formatira srpski tekući račun u 18 cifara za NBS IPS QR standard."""
    digits = re.sub(r"\D", "", acc_raw or "")
    if "-" in (acc_raw or ""):
        parts = [re.sub(r"\D", "", p) for p in acc_raw.split("-")]
        if len(parts) == 3 and len(parts[0]) == 3 and len(parts[2]) == 2:
            return parts[0] + parts[1].zfill(13) + parts[2]
    if len(digits) == 18:
        return digits
    return ""


def _make_qr_png_buffer(data_str: str, box_size: int = 4, border: int = 1) -> io.BytesIO:
    """
    Generiše čist RGB PNG bafer QR koda.
    .convert('RGB') sprečava fpdf2 bug sa kosim/izlomljenim linijama kod 1-bitnih slika.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img_qr.save(buf, format="PNG")
    buf.seek(0)
    return buf


class InvoicePDF(FPDF):
    """Podklasa FPDF za fakturu sa podacima i opcionim logom firme kupca."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cfg = get_app_settings()

    def header(self):
        has_custom_logo = CUSTOM_LOGO_PATH.exists()
        text_x = 10

        if has_custom_logo:
            try:
                self.image(str(CUSTOM_LOGO_PATH), x=10, y=9, w=34)
                text_x = 48
            except Exception:
                text_x = 10

        company_name = (self.cfg.get("company_name") or "Moja Firma").strip()
        address = (self.cfg.get("company_address") or "").strip()
        pib = (self.cfg.get("company_pib") or "").strip()
        mb = (self.cfg.get("company_mb") or "").strip()
        bank_acc = (self.cfg.get("company_bank_acc") or "").strip()

        self.set_xy(text_x, 9)
        self.set_font("DejaVu", "B", 15)
        self.set_text_color(*CRNA)
        self.cell(95, 7, company_name[:40], ln=True, align="L")

        self.set_x(text_x)
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(*SIVA)

        details = []
        if address:
            details.append(address)
        if pib:
            details.append(f"PIB: {pib}")
        if mb:
            details.append(f"MB: {mb}")
        if details:
            self.cell(95, 4.5, " · ".join(details)[:65], ln=True, align="L")

        if bank_acc:
            self.set_x(text_x)
            self.cell(95, 4.5, f"Tekući račun: {bank_acc}", ln=True, align="L")

        # Linija je spuštena na y=34 da nikada ne pređe preko desnog bloka (Datum/Kanal/Status/Valuta)
        self.set_draw_color(*CRNA)
        self.set_line_width(0.6)
        line_y = max(self.get_y() + 3, 34)
        self.line(10, line_y, 200, line_y)
        self.set_y(line_y + 6)

    def footer(self):
        company_name = (self.cfg.get("company_name") or "MicroStock").strip()
        self.set_y(-20)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(*SIVA)
        self.cell(
            0, 5,
            f"{company_name} · generisano {datetime.now().strftime('%d.%m.%Y %H:%M')} · Hvala na poverenju!",
            align="C"
        )


def generate_invoice_pdf(order, items, subtotal, fee, total,
                          currency="RSD", currency_symbol="din"):
    """Vraća bytes PDF fajla za datu narudžbinu u izabranoj valuti."""

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")

    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))

    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ===== Zaglavlje desno =====
    pdf.set_xy(110, 9)
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(*CRNA)
    pdf.cell(90, 6.5, f"RAČUN #{order['id']:05d}", align="R", ln=True)
    pdf.set_x(110)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(*SIVA)

    created = order.get("created_at")
    if hasattr(created, "strftime"):
        created_str = created.strftime("%d.%m.%Y")
    elif created:
        created_str = str(created)[:10]
    else:
        created_str = "—"

    pdf.cell(90, 4.2, f"Datum: {created_str}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 4.2, f"Kanal: {order['channel']}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 4.2, f"Status: {order['status']}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 4.2, f"Valuta: {currency}", align="R", ln=True)
    pdf.set_text_color(0, 0, 0)

    pdf.set_y(40)

    # ===== Info box =====
    pdf.set_fill_color(*SVETLO_SIVA)
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_text_color(*SIVA)
    pdf.cell(90, 6, "  KUPAC", ln=False, fill=True)
    pdf.cell(10, 6, "", ln=False)
    pdf.cell(90, 6, "  PODACI O RAČUNU", ln=True, fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(90, 7, "  " + str(order["customer_name"]), ln=False)
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(10, 7, "", ln=False)
    pdf.cell(90, 7, f"  Broj: #{order['id']:05d}", ln=True)

    pdf.set_font("DejaVu", "", 10)
    if order.get("note"):
        pdf.cell(90, 6, "  " + str(order["note"])[:50], ln=False)
    else:
        pdf.cell(90, 6, "", ln=False)
    pdf.cell(10, 6, "", ln=False)
    pdf.cell(90, 6, f"  Izvor: {order.get('source') or 'manual'}", ln=True)

    if order.get("external_id"):
        pdf.cell(90, 6, "", ln=False)
        pdf.cell(10, 6, "", ln=False)
        pdf.cell(90, 6, f"  Ref: {order['external_id']}", ln=True)

    pdf.ln(6)

    # ===== Tabela stavki =====
    pdf.set_fill_color(*CRNA)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 9)
    pdf.cell(110, 8, "  PROIZVOD", fill=True)
    pdf.cell(20, 8, "KOL.", fill=True, align="C")
    pdf.cell(30, 8, f"CENA ({currency_symbol})", fill=True, align="R")
    pdf.cell(30, 8, "UKUPNO  ", fill=True, align="R", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "", 10)
    fill = False
    for it in items:
        if fill:
            pdf.set_fill_color(250, 250, 250)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(110, 8, "  " + str(it["product_name"])[:45], fill=True)
        pdf.cell(20, 8, str(it["qty"]), fill=True, align="C")
        pdf.cell(30, 8, f"{float(it['unit_price']):.2f}", fill=True, align="R")
        pdf.cell(30, 8, f"{float(it['qty']) * float(it['unit_price']):.2f}  ", fill=True, align="R", ln=True)
        fill = not fill

        pdf.set_font("DejaVu", "I", 8)
        pdf.set_text_color(*SIVA)
        pdf.cell(110, 4, "  " + str(it["sku"]), ln=True)
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # ===== Suma =====
    y_totals_start = pdf.get_y()
    pdf.set_x(120)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*SIVA)
    pdf.cell(45, 6, "Osnova:", align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(35, 6, f"{float(subtotal):.2f} {currency_symbol}", align="R", ln=True)

    if float(fee) > 0:
        pdf.set_x(120)
        pdf.set_text_color(*SIVA)
        pdf.cell(45, 6, f"Provizija ({order['fee_percent']}%):", align="R")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(35, 6, f"{float(fee):.2f} {currency_symbol}", align="R", ln=True)

    pdf.set_x(120)
    pdf.set_draw_color(*CRNA)
    pdf.set_line_width(0.5)
    y = pdf.get_y() + 1
    pdf.line(120, y, 200, y)
    pdf.ln(2)

    pdf.set_x(120)
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_text_color(*CRNA)
    pdf.cell(45, 8, "UKUPNO:", align="R")
    pdf.cell(35, 8, f"{float(total):.2f} {currency_symbol}", align="R", ln=True)

    # ===== NBS IPS QR KOD =====
    nbs_acc = _format_nbs_account(pdf.cfg.get("company_bank_acc", ""))
    if nbs_acc and currency == "RSD" and float(total) > 0:
        try:
            company_clean = (pdf.cfg.get("company_name") or "Firma")[:35].replace("|", " ")
            amount_str = f"RSD{float(total):.2f}".replace(".", ",")
            ips_payload = (
                f"K:PR|V:01|C:1|R:{nbs_acc}|N:{company_clean}"
                f"|I:{amount_str}|SF:289|S:Racun br {order['id']:05d}"
            )
            qr_buf = _make_qr_png_buffer(ips_payload, box_size=3, border=1)

            pdf.image(qr_buf, x=12, y=y_totals_start, w=28, h=28)
            pdf.set_xy(42, y_totals_start + 8)
            pdf.set_font("DejaVu", "B", 8)
            pdf.set_text_color(*CRNA)
            pdf.cell(60, 4, "NBS IPS QR Plaćanje", ln=True)
            pdf.set_x(42)
            pdf.set_font("DejaVu", "", 7)
            pdf.set_text_color(*SIVA)
            pdf.cell(60, 4, "Skenirajte aplikacijom vaše banke", ln=True)
        except Exception:
            pass

    pdf.ln(10)
    pdf.set_x(120)
    pdf.set_text_color(*ZELENA)
    pdf.set_draw_color(*ZELENA)
    pdf.set_line_width(0.5)
    pdf.set_font("DejaVu", "B", 10)
    status_label = "PLAĆENO" if str(order.get("status", "")).lower() in ("paid", "completed", "shipped", "done", "plaćeno") else str(order.get("status", "U OBRADI")).upper()
    pdf.cell(40, 10, status_label, border=1, align="C", ln=True)

    return bytes(pdf.output())


# ============================================================
# ANALYTICS PDF
# ============================================================

def generate_analytics_pdf(kpi, channels, products, loss, customers,
                            days=None, lang="sr", currency="RSD",
                            currency_symbol="din",
                            title="Analytics"):
    """Vraća bytes PDF izveštaja analitike."""
    from datetime import datetime as _dt

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_xy(10, 38)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, title, ln=True, align="L")

    pdf.set_x(10)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*SIVA)
    period_label = f"Period: {days} dana" if days else "Period: sve vreme"
    pdf.cell(0, 5, f"{period_label} · Generisano: {_dt.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align="L")
    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, "KPI", ln=True)

    kpi_rows = [
        ("Prihod:",       f"{float(kpi.get('revenue', 0)):.2f} {currency_symbol}"),
        ("Provizije:",    f"{float(kpi.get('fees', 0)):.2f} {currency_symbol}"),
        ("Trošak robe:",  f"{float(kpi.get('cost', 0)):.2f} {currency_symbol}"),
        ("Dostava:",      f"{float(kpi.get('shipping', 0)):.2f} {currency_symbol}"),
        ("Profit:",       f"{float(kpi.get('profit', 0)):.2f} {currency_symbol}"),
        ("Marža:",        f"{kpi.get('margin', 0)}%"),
        ("Narudžbina:",   f"{kpi.get('orders', 0)}"),
    ]
    for label, value in kpi_rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(60, 6, label)
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 6, value, ln=True)

    if channels:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Prodaja po kanalima", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        headers = [("Kanal", 35), ("Prihod", 30), ("Proviz.", 25),
                   ("Trošak", 25), ("Dostava", 25), ("Profit", 30), ("Nar.", 15)]
        for h, w in headers:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for c in channels:
            pdf.cell(35, 6, str(c.get("channel_name", ""))[:20])
            pdf.cell(30, 6, f"{float(c.get('revenue', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('fees', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('cost', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('shipping', 0)):.2f}", align="R")
            pdf.cell(30, 6, f"{float(c.get('profit', 0)):.2f}", align="R")
            pdf.cell(15, 6, str(c.get("orders", 0)), align="C")
            pdf.ln()

    if products:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 8, "Top proizvodi", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("SKU", 30), ("Naziv", 70), ("Kom", 20), ("Prihod", 30), ("Profit", 30)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for p in products[:20]:
            pdf.cell(30, 6, str(p.get("sku", ""))[:15])
            pdf.cell(70, 6, str(p.get("product_name", ""))[:35])
            pdf.cell(20, 6, str(p.get("units", 0)), align="C")
            pdf.cell(30, 6, f"{float(p.get('revenue', 0)):.2f}", align="R")
            pdf.cell(30, 6, f"{float(p.get('profit', 0)):.2f}", align="R")
            pdf.ln()

    if customers:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 8, "Top kupci", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Kupac", 120), ("Narudžbina", 30), ("Ukupno", 30)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for c in customers[:20]:
            pdf.cell(120, 6, str(c.get("customer_name", ""))[:50])
            pdf.cell(30, 6, str(c.get("orders", 0)), align="C")
            pdf.cell(30, 6, f"{float(c.get('revenue', 0)):.2f}", align="R")
            pdf.ln()

    return bytes(pdf.output())


# ============================================================
# PROJECT PDF
# ============================================================

def generate_project_pdf(project, time_entries, expenses,
                          currency_symbol="din", lang="sr"):
    """Vraća bytes PDF izveštaja projekta."""
    from datetime import datetime as _dt

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_xy(10, 38)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, f"Projekat: {project.get('name', '')}", ln=True, align="L")

    pdf.set_x(10)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*SIVA)
    pdf.cell(0, 5, f"Kod: {project.get('code', '—')}  ·  Klijent: {project.get('client', '—')}", ln=True, align="L")
    pdf.set_x(10)
    pdf.cell(0, 5, f"Rok: {project.get('deadline', '—')}  ·  Status: {project.get('status', '—')}", ln=True, align="L")
    pdf.set_x(10)
    pdf.cell(0, 5, f"Generisano: {_dt.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align="L")

    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, "KPI", ln=True)

    kpi_rows = [
        ("Ugovorena vrednost:",  f"{float(project.get('contract_value', 0)):.2f} {currency_symbol}"),
        ("Ukupan trošak:",       f"{float(project.get('total_cost', 0)):.2f} {currency_symbol}"),
        ("Profit:",              f"{float(project.get('profit', 0)):.2f} {currency_symbol}"),
        ("Marža:",               f"{project.get('margin', 0)}%"),
        ("Radni sati:",          f"{float(project.get('total_hours', 0)):.1f} h"),
    ]
    for label, value in kpi_rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(70, 6, label)
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 6, value, ln=True)

    if time_entries:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Radni sati", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Datum", 30), ("Član", 60), ("Sati", 20), ("Opis", 80)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for t in time_entries:
            pdf.cell(30, 6, str(t.get("entry_date", ""))[:10])
            pdf.cell(60, 6, str(t.get("member_name", ""))[:30])
            pdf.cell(20, 6, f"{float(t.get('hours', 0)):.2f}", align="C")
            pdf.cell(80, 6, str(t.get("description", ""))[:50])
            pdf.ln()

    if expenses:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Troškovi", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Datum", 30), ("Kategorija", 40), ("Opis", 80), ("Iznos", 40)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for e in expenses:
            pdf.cell(30, 6, str(e.get("expense_date", ""))[:10])
            pdf.cell(40, 6, str(e.get("category", ""))[:20])
            pdf.cell(80, 6, str(e.get("description", ""))[:50])
            pdf.cell(40, 6, f"{float(e.get('amount', 0)):.2f} {currency_symbol}", align="R")
            pdf.ln()

    return bytes(pdf.output())


# ============================================================
# NALEPNICE SA QR KODOM (Ispravljen RGB QR + Unicode font)
# ============================================================

def generate_product_labels_pdf(product, count=24, currency="din"):
    """Kreira A4 tabak sa nalepnicama (3 kolone x 8 redova = 24 po stranici)."""
    # Zaštita ako su zalihe 0 ili u minusu (npr. -3 kom)
    try:
        count = int(float(count))
    except (ValueError, TypeError):
        count = 24
    if count <= 0:
        count = 1

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    cols = 3
    rows = 8
    label_w = 64
    label_h = 34
    margin_x = 9
    margin_y = 12

    # RGB QR kod (kristalno oštar u fpdf2)
    qr_buffer = _make_qr_png_buffer(str(product["sku"]), box_size=6, border=1)

    for i in range(count):
        index_on_page = i % (cols * rows)
        if i > 0 and index_on_page == 0:
            pdf.add_page()

        col = index_on_page % cols
        row = index_on_page // cols

        x = margin_x + col * label_w
        y = margin_y + row * label_h

        pdf.set_draw_color(210, 210, 210)
        pdf.rect(x, y, label_w - 2, label_h - 2)

        qr_buffer.seek(0)
        pdf.image(qr_buffer, x=x + 2, y=y + 3, w=22, h=22)

        pdf.set_text_color(20, 20, 20)
        pdf.set_font("DejaVu", "B", 9)
        pdf.set_xy(x + 26, y + 4)
        pdf.cell(label_w - 29, 5, str(product["sku"])[:18], ln=0)

        pdf.set_font("DejaVu", "", 8)
        pdf.set_xy(x + 26, y + 10)
        name_str = str(product.get("name") or "")
        name_short = (name_str[:20] + "..") if len(name_str) > 22 else name_str
        pdf.cell(label_w - 29, 5, name_short, ln=0)

        pdf.set_font("DejaVu", "B", 10)
        pdf.set_xy(x + 26, y + 17)
        cena = f"{float(product.get('price') or 0):,.0f} {currency}".replace(",", ".")
        pdf.cell(label_w - 29, 6, cena, ln=0)

    return bytes(pdf.output())