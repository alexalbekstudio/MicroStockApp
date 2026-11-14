# mailer.py
"""
Email notifikacije za MicroStockApp (Standalone Edition).
- Čita SMTP parametre direktno iz baze (app_settings) koje kupac sam unese.
- Ne zavisi od .env fajla niti od programerovog Gmail naloga.
- Sve funkcije vraćaju True/False i nikada ne ruše request.
"""
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import current_app
from flask_mail import Mail

from database import get_app_settings

mail = Mail()


def init_mail(app):
    """Zadržano zbog kompatibilnosti sa app.py."""
    mail.init_app(app)


def _get_smtp_config():
    """Povlači trenutna SMTP podešavanja kupca iz baze (app_settings)."""
    s = get_app_settings()
    server = (s.get("smtp_server") or os.getenv("MAIL_SERVER") or "smtp.gmail.com").strip()
    port = int(s.get("smtp_port") or os.getenv("MAIL_PORT") or 587)
    use_tls = bool(s.get("smtp_use_tls", 1))
    user = (s.get("smtp_username") or os.getenv("MAIL_USERNAME") or "").strip()
    password = (s.get("smtp_password") or os.getenv("MAIL_PASSWORD") or "").strip()
    company = (s.get("company_name") or "MicroStock").strip()
    alert_to = (s.get("alert_email") or os.getenv("ALERT_EMAIL") or user).strip()

    return {
        "server": server,
        "port": port,
        "use_tls": use_tls,
        "user": user,
        "password": password,
        "sender": f"{company} <{user}>" if user else "",
        "alert_to": alert_to,
        "company": company,
    }


def _send_raw_email(to_email, subject, html, text=None, pdf_bytes=None, pdf_filename=None):
    """Dinamičko slanje emaila pomoću podataka iz app_settings tabele."""
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"] or not to_email:
        if current_app:
            current_app.logger.warning("MAIL: SMTP nije podešen u Settings-u, preskačem slanje.")
        return False

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = cfg["sender"]
        msg["To"] = to_email

        alt = MIMEMultipart("alternative")
        plain_body = text or _html_to_text(html)
        alt.attach(MIMEText(plain_body, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)

        if pdf_bytes and pdf_filename:
            part = MIMEApplication(pdf_bytes, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
            msg.attach(part)

        with smtplib.SMTP(cfg["server"], cfg["port"], timeout=15) as server:
            if cfg["use_tls"]:
                server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)

        if current_app:
            current_app.logger.info(f"MAIL: poslato -> {to_email} | {subject}")
        return True
    except Exception as e:
        if current_app:
            current_app.logger.error(f"MAIL greška: {e}")
        else:
            print(f"MAIL greška: {e}")
        return False


def _send(subject, html, text=None):
    cfg = _get_smtp_config()
    return _send_raw_email(cfg["alert_to"], subject, html, text=text)


def _send_to(to_email, subject, html):
    return _send_raw_email(to_email, subject, html)


def _html_to_text(html):
    return re.sub(r"<[^>]+>", "", html).strip()


# ============================================================
# ŠABLON (Personalizovan prema firmi kupca)
# ============================================================

def _wrap(title, color, body_html):
    cfg = _get_smtp_config()
    company_name = cfg["company"]
    contact_email = cfg["alert_to"] or cfg["user"]
    DARK = "#0f172a"

    footer_contact = (
        f'<a href="mailto:{contact_email}" style="color:#6366f1;text-decoration:none">{contact_email}</a>'
        if contact_email else company_name
    )

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;
                border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">

      <div style="background:{DARK};padding:20px;text-align:center;color:#ffffff;
                  font-size:20px;font-weight:700;letter-spacing:0.5px">
        📦 {company_name}
      </div>

      <div style="background:{color};color:#fff;padding:12px 20px 16px;
                  text-align:center;font-size:16px;font-weight:700">
        {title}
      </div>

      <div style="padding:20px;color:#111827;font-size:14px;line-height:1.6">
        {body_html}
      </div>

      <div style="background:#f9fafb;color:#6b7280;padding:12px 20px;
                  font-size:12px;border-top:1px solid #e5e7eb;text-align:center">
        Automatska notifikacija iz vašeg MicroStock sistema.<br>
        {footer_contact}
      </div>
    </div>
    """


# ============================================================
# NOTIFIKACIJE I IZVEŠTAJI
# ============================================================

def send_project_warn(project, pct, spent, budget):
    subject = f"⚠️ Projekat '{project['name']}' je na {pct:.0f}% budžeta"
    body = f"""
      <p>Projekat <b>{project['name']}</b>
         ({project.get('client') or 'bez klijenta'}) je prešao <b>80% budžeta</b>.</p>
      <table style="border-collapse:collapse;margin:12px 0">
        <tr><td style="padding:4px 12px 4px 0"><b>Budžet:</b></td><td>{budget:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Potrošeno:</b></td><td>{spent:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Iskorišćeno:</b></td><td><b>{pct:.1f}%</b></td></tr>
      </table>
      <p>Preporuka: proveri troškove i preostale sate tima.</p>
    """
    return _send(subject, _wrap("Alarm budžeta", "#f59e0b", body))


def send_project_danger(project, pct, spent, budget):
    subject = f"🚨 PREKORAČENJE: Projekat '{project['name']}' je prekoračio budžet"
    body = f"""
      <p>Projekat <b>{project['name']}</b>
         ({project.get('client') or 'bez klijenta'}) je prekoračio <b>100% budžeta</b>!</p>
      <table style="border-collapse:collapse;margin:12px 0">
        <tr><td style="padding:4px 12px 4px 0"><b>Budžet:</b></td><td>{budget:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Potrošeno:</b></td><td>{spent:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Prekoračenje:</b></td>
            <td><b style="color:#dc2626">{spent - budget:.2f} €</b></td></tr>
      </table>
    """
    return _send(subject, _wrap("Kritično prekoračenje", "#dc2626", body))


def send_low_stock_digest(products):
    if not products:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>{p['sku']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{p['name']}</td>"
        f"<td style='padding:4px 12px 4px 0;color:#dc2626'><b>{p['stock']}</b></td>"
        f"<td style='padding:4px 12px 4px 0'>{p.get('low_stock_threshold', 5)}</td></tr>"
        for p in products
    )
    subject = f"📦 Niske zalihe: {len(products)} proizvod(a)"
    body = f"""
      <p>Sledeći proizvodi imaju niske zalihe:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">SKU</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Naziv</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Stanje</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Prag</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Niske zalihe", "#2563eb", body))


def send_pending_orders_digest(orders, days):
    if not orders:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>#{o['id']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{o.get('customer') or '—'}</td>"
        f"<td style='padding:4px 12px 4px 0'>{o.get('status')}</td>"
        f"<td style='padding:4px 12px 4px 0'>{str(o.get('created_at', ''))[:10]}</td></tr>"
        for o in orders
    )
    subject = f"⏳ {len(orders)} narudžbina čeka duže od {days} dana"
    body = f"""
      <p>Sledeće narudžbine nisu promenile status duže od <b>{days} dana</b>:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">#</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Kupac</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Status</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Datum</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Narudžbine koje čekaju", "#f59e0b", body))


def send_deadlines_digest(projects):
    if not projects:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>{p['name']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{p.get('client') or '—'}</td>"
        f"<td style='padding:4px 12px 4px 0'>{str(p.get('deadline', ''))[:10]}</td></tr>"
        for p in projects
    )
    subject = f"📅 {len(projects)} projekat(a) sa rokom u narednih 14 dana"
    body = f"""
      <p>Sledeći projekti imaju rok u narednih <b>14 dana</b>:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">Projekat</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Klijent</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Rok</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Rokovi projekata", "#7c3aed", body))


def send_test_email():
    return _send(
        "✅ MicroStock test email",
        _wrap("Test konekcije", "#10b981",
              "<p>Vaša SMTP email podešavanja su ispravno konfigurisana! 🎉</p>")
    )


def send_report_email(to_email, subject, html_body, pdf_bytes=None, pdf_filename=None):
    return _send_raw_email(to_email, subject, html_body, pdf_bytes=pdf_bytes, pdf_filename=pdf_filename)


def send_password_reset(to_email, reset_url):
    subject = "🔐 Reset šifre"
    body = f"""
      <p>Zdravo,</p>
      <p>Zatražen je reset šifre za vaš nalog.</p>
      <p style="margin:24px 0">
        <a href="{reset_url}"
           style="background:#6366f1;color:#fff;padding:12px 24px;
                  border-radius:6px;text-decoration:none;font-weight:600">
          Postavi novu šifru
        </a>
      </p>
      <p style="background:#f3f4f6;padding:8px 12px;border-radius:4px;
                font-family:monospace;font-size:12px;word-break:break-all">
        {reset_url}
      </p>
    """
    return _send_to(to_email, subject, _wrap("Reset šifre", "#6366f1", body))


def send_subscription_expiring(*args, **kwargs):
    return True


def send_subscription_expiring_admin(*args, **kwargs):
    return True


def send_package_limit_warning(*args, **kwargs):
    return True


def send_admin_daily_report(kpi, logins, features, expiring):
    subject = f"📊 Dnevni izveštaj sistema — {kpi.get('logins_today', 0)} prijava danas"
    body = f"""
      <h3>📊 Današnja aktivnost</h3>
      <p>Ukupno korisnika: <b>{kpi.get('total_users', 1)}</b></p>
      <p>Akcije (30d): <b>{kpi.get('actions_period', 0)}</b></p>
    """
    return _send(subject, _wrap("Dnevni izveštaj", "#6366f1", body))