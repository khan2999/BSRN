import sys
from config import Config
from discovery import run_discovery_service
from multiprocessing.connection import Listener
import os

if __name__ == "__main__":
    """
    @file discovery_main.py
    @brief Startskript für den Discovery-Service als Singleton pro Host/Port.
    @details Verwendet ein Lockfile, um sicherzustellen, dass pro Port nur eine Instanz läuft.
    @usage python3 discovery_main.py <config.toml> [ipc_port]
    """
    # Mindestanzahl an Argumenten prüfen (Config-Datei erforderlich)
    if len(sys.argv) < 2:
        print("Usage: python3 discovery_main.py <config.toml> [ipc_port]")
        sys.exit(1)

    # Lade TOML-Konfiguration (enthält whoisport u. a.)
    config = Config(sys.argv[1])
    # Bestimme IPC-Port: Entweder Parameter oder `whoisport` aus Config
    ipc_port = int(sys.argv[2]) if len(sys.argv) > 2 else config.whoisport
    # Lockfile-Pfad für Singleton-Prüfung
    lockfile = f"/tmp/chat_discovery_{ipc_port}.lock"

    # Singleton-Mechanismus: Lockfile anlegen, Fehler bei existierendem File
    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        # Wenn Lockfile bereits existiert, läuft ein Discovery bereits
        print(f"Discovery auf Port {ipc_port} läuft bereits.")
        sys.exit(1)

    # IPC-Server für UI: Listener auf der angegebenen Adresse
    address = ('localhost', ipc_port)
    with Listener(address, authkey=b'ipc_secret') as listener:
        print(f"[Discovery] IPC-Listener auf {address}")
        # Warte auf UI-Verbindung via IPC
        conn = listener.accept()
        print("[Discovery] UI verbunden, starte Service …")
        # Starte Discovery-Dienst, verwendet dieselbe Pipe für Commands und Events
        run_discovery_service(conn, conn, config)

    # Beim Beenden Lockfile schließen und entfernen
    os.close(fd)
    os.unlink(lockfile)
