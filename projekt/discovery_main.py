##
# @file discovery_main.py
# @brief Einstiegspunkt für den Discovery-Service im dezentralen Chat-Programm.
#
# @details
# Dieses Skript dient als separater Startprozess für den UDP-basierten Discovery-Service.
# Es stellt sicher, dass auf jedem Host pro Port nur eine Instanz des Discovery-Moduls läuft.
# Dies wird durch ein Lockfile im temporären Verzeichnis realisiert.
#
# Nach dem Start öffnet der Dienst einen IPC-Listener zur Kommunikation mit der Benutzeroberfläche.
# Sobald die Verbindung zur UI steht, wird der Discovery-Service gestartet, der sich um die
# Broadcast-basierte Teilnehmererkennung im lokalen Netzwerk kümmert.
#
# @usage
#   python3 discovery_main.py <config.toml> [ipc_port]
#
# @section Komponenten
# - *Config*: Lädt Benutzer- und Netzwerkparameter aus einer TOML-Datei.
# - *run_discovery_service*: Discovery-Funktion aus dem discovery-Modul.
# - *Listener*: Stellt IPC-Verbindung zur Benutzeroberfläche (UI) her.
#
# @note Der Dienst sollte pro Gerät und Port nur einmal gestartet werden.
#
# @author Ismet Algül, Aysenur Algül, Enes Kurutay, Ugur Can, Nasratullah Ahmadzai
# @date Juni 2025

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
