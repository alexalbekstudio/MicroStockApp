# desktop.py
"""
MicroStock Standalone Desktop Launcher (kao Electron, ali lakši i brži).
- Automatski koristi lokalnu SQLite bazu (microstock_local.db) ako DATABASE_URL nije podešen.
- Podiže Flask server u pozadini na slobodnom lokalnom portu.
- Otvara čist Desktop prozor aplikacije bez adresne linije pregledača.
"""

import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser

# Osiguraj da radni direktorijum bude folder aplikacije (bitno za PyInstaller .exe)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

from app import app


def _find_free_port(default_port=5000) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", default_port)) != 0:
            return default_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_server(port: int):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def main():
    port = _find_free_port(5000)
    url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    # Sačekaj da Flask server postane dostupan
    for _ in range(30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.15)

    # 1. Pokušaj nativni Desktop prozor preko pywebview (ako je instaliran)
    try:
        import webview
        webview.create_window(
            "MicroStock Standalone",
            url,
            width=1360,
            height=860,
            min_size=(1024, 680),
        )
        webview.start()
        sys.exit(0)
    except ImportError:
        pass

    # 2. Fallback: Windows Edge / Chrome u "--app" režimu (izgleda identično kao Electron prozor)
    app_opened = False
    for browser_cmd in ("msedge", "chrome"):
        try:
            subprocess.Popen(f"start {browser_cmd} --app={url}", shell=True)
            app_opened = True
            break
        except Exception:
            continue

    if not app_opened:
        webbrowser.open(url)

    print(f"✅ MicroStock Desktop radi na {url} (Pritisni Ctrl+C za izlaz)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()