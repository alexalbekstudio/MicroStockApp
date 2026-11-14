# 📦 MicroStockApp (Standalone & Self-Hosted Edition)

**Samostalni softver za vođenje zaliha, narudžbina, projekata i finansija — bez mesečne pretplate.**
Instaliraj na svoj računar (Windows Desktop) ili sopstveni server (Docker / PostgreSQL / SQLite) uz potpunu kontrolu nad sopstvenim podacima.

---

## ✨ Šta MicroStockApp radi (Modularna arhitektura)

1. **📦 Zalihe i narudžbine (Core)** — proizvodi, sastavnice/recepture, narudžbine, PDF fakture sa logom i QR kodom.
2. **📊 Analitika prodaje** — prihod, čist profit, marža po kanalu prodaje, top proizvodi i detekcija gubitaša.
3. **🏢 Nabavka, dobavljači i kapital** — imenik dobavljača, ulazne fakture, praćenje dugovanja i tokova kapitala.
4. **📁 Praćenje projekata (Agencijski modul)** — klijenti, utrošeni sati tima, troškovi po projektu i kontrola budžeta.

---

## 💰 Cene i paketi (Jednokratna kupovina — Trajna licenca)

Platiš jednom, koristiš zauvek na svom računaru ili serveru — bez skrivenih mesečnih troškova.

### 🟢 1. Core (Osnovni model) — **49€ jednokratno**
Idealan za male prodavce i zanatlije kojima treba red u magacinu i brzo fakturisanje.
- **Zalihe i proizvodi** (neograničen broj artikala + alarmi za niske zalihe)
- **Narudžbine i PDF fakture** sa vašim logom i podacima firme
- **Osnovni pregled prodaje** i izvoz podataka (CSV)
- **Multi-currency** (RSD, EUR, USD) i dvojezični interfejs (SR/EN)
- **1 korisnik (Lokalna Desktop / SQLite instalacija)**

### 🔵 2. Pro (+ Poslovni dodaci) — **99€ jednokratno** ⭐ Najčešći izbor
Za firme koje žele potpunu kontrolu nad maržama, dobavljačima i više prodajnih kanala.
- **Sve iz Core paketa**
- **➕ Modul: Nabavka i dobavljači** (ulazni računi, kalkulacija nabavne cene, evidencija duga)
- **➕ Modul: Napredna analitika i Kapital** (čist profit, gubitaši, grafikoni po kanalima, uplate/isplate)
- **➕ Modul: Masovni CSV uvoz** (Etsy, Shopify, generički CSV) + **QR skener**
- **➕ Sopstveni SMTP i NBS API** (slanje izveštaja i alarma direktno sa vašeg mejla)
- **Do 5 korisnika** (Mrežni ili lokalni rad)

### 🟣 3. Ultimate (Komplet funkcionalnost + Server/Kod) — **179€ jednokratno**
Kompletno rešenje za timove, agencije i firme koje žele sve module i instalaciju na sopstvenom serveru.
- **Sve iz Pro paketa (Svi moduli otključani)**
- **➕ Modul: Praćenje projekata i radnih sati** (za agencije, radionice i uslužne delatnosti)
- **➕ Neograničen broj korisnika i uloga** (Admin, Manager, Viewer)
- **➕ Self-Hosted Server Setup** (Docker + PostgreSQL podrška za rad sa više lokacija + automatski dnevni backup)
- **➕ Pristup izvornom kodu** za interne potrebe firme i prioritetna pomoć pri podešavanju

*(Moguća je i pojedinačna kupovina dodataka uz Core paket: Modul Nabavka/Dobavljači **+30€**, Modul Projekti **+30€**, Modul Napredna Analitika & CSV **+25€**).*

---

## 🛡️ Potpuna nezavisnost (Zero-Dependency)

- ✅ **100% Vaši podaci** — baza se nalazi na vašem računaru ili vašem serveru.
- ✅ **Ugrađen Setup Wizard (Settings)** — sami unosite podatke svoje firme, svoj Gmail App Password za notifikacije i NBS API ključ direktno iz interfejsa aplikacije.
- ✅ **Automatska inicijalizacija baze** — aplikacija pri prvom pokretanju sama kreira sve tabele i strukturu.
- ✅ **Offline & PWA podrška** — radi u lokalnoj mreži čak i kada nestane internet.

---

## 🛠️ Tehnologije

- **Backend:** Python 3.12 + Flask 3
- **Baza podataka:** Dual-mode podrška (SQLite za Desktop / PostgreSQL za Server)
- **Frontend:** Čist HTML5, CSS3, JavaScript (PWA)
- **Dokumenti:** FPDF2 (PDF fakture i izveštaji) + QRCode generator

---

## 📞 Kontakt i naručivanje

- **Email:** [alexalbekstudio.design@gmail.com](mailto:alexalbekstudio.design@gmail.com)
- **Web:** [alexandar.studio](https://alexandar.studio)
- **Studio:** ALEXANDAR Studio | © 2026 Sva prava zadržana.