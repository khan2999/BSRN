##
# @file network_main.py
# @brief Startskript für den Network-Service-Prozess.
# @details Dieses Modul wird als separates Skript aufgerufen, um den Netzwerkdienst des
# Chatprogramms zu starten. Es stellt eine IPC-Verbindung zur Benutzeroberfläche her
# und übergibt dann die Kontrolle an den eigentlichen Netzwerkdienst.
#
# Wird typischerweise aufgerufen durch:
# @code
# python3 network_main.py <config.toml> [ipc_port]
# @endcode
#
# @author Gruppe A11
# @date 2025

import sys
from config import Config
from network import run_network_service
from multiprocessing.connection import Listener

if __name__ == "__main__":
    """
    @brief Startskript für den Network-Service-Prozess.
    @details Wartet auf UI-Verbindung per IPC und ruft anschließend run_network_service auf.
    @usage python3 network_main.py <configfile.toml> [ipc_port]
    """
    # Überprüfe Kommandozeilen-Parameter: mindestens Pfad zur Config
    if len(sys.argv) < 2:
        print("Usage: python3 network_main.py <configfile.toml> [ipc_port]")
        sys.exit(1)

    # Lade Konfiguration (TOML-Datei enthält Handle, Port-Range, whoisport, autoreply, imagepath)
    config = Config(sys.argv[1])
    # Lese optionalen IPC-Port aus Parameter oder verwende Default 6001
    ipc_port = int(sys.argv[2]) if len(sys.argv) > 2 else 6001
    address = ('localhost', ipc_port)

    # Richte IPC-Listener zum Empfang von UI-Kommandos ein
    with Listener(address, authkey=b'ipc_secret') as listener:
        # Informiere über Start des IPC-Servers
        print(f"[Network] IPC-Listener läuft auf {address}")
        # Warte auf eintreffende UI-Verbindung
        conn = listener.accept()
        print("[Network] UI verbunden, starte Service …")
        # Führe den Network-Service aus: kommuniziert mit UI über dieselbe Pipe (conn)
        run_network_service(conn, conn, config)
