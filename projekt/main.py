# main.py – Startskript für Discovery-, Network- und UI-Prozesse

import sys
import multiprocessing
import time

from config import Config
from discovery import run_discovery_service
from network   import run_network_service
from ui        import run_ui

def main():
    """
    @brief Hauptfunktion: Initialisiert die Konfiguration und startet die drei Hauptprozesse.
    @detail Lädt die TOML-Konfigurationsdatei (Handle, Port-Range, Autoreply, Image-Pfad),
            richtet bidirektionale Pipes für IPC ein, startet Discovery- und Network-Services
            als Hintergrundprozesse (Daemons) und führt die UI-Schleife im Hauptprozess aus.
    """
    # Überprüfen der Anzahl der Kommandozeilenargumente
    if len(sys.argv) != 2:
        print("Usage: python3 main.py <alice.toml|bob.toml>")
        sys.exit(1)

    # Konfigurationsdatei laden: enthält Benutzer-Handle und Netzwerkparameter
    config = Config(sys.argv[1])

    # IPC-Pipes anlegen: jeweils ein Sende- und Empfangs-Ende für UI ↔ Network und UI ↔ Discovery
    net_cmd, net_recv   = multiprocessing.Pipe()  # UI → Network: sendet Aktionen
    net_send, net_evt   = multiprocessing.Pipe()  # Network → UI: liefert Events zurück
    disc_cmd, disc_recv = multiprocessing.Pipe()  # UI → Discovery: JOIN/WHO/LEAVE
    disc_send, disc_evt = multiprocessing.Pipe()  # Discovery → UI: liefert Nutzerlisten-Updates

    # 1) Discovery-Dienst starten:
    #    Verantwortlich für Broadcast-basierte Teilnehmererkennung und Registry-Pflege.
    disc_proc = multiprocessing.Process(
        target=run_discovery_service,
        args=(disc_recv, disc_send, config),
        daemon=True  # läuft im Hintergrund und wird beim Hauptprozess-Ende automatisch beendet
    )
    disc_proc.start()

    # Kurze Pause, damit der Discovery-Service sein UDP-Socket binden und lauschen kann
    time.sleep(0.1)

    # 2) Network-Dienst starten:
    #    Verantwortlich für TCP-Verbindungen (MSG) und UDP-Bildübertragungen (IMG).
    net_proc = multiprocessing.Process(
        target=run_network_service,
        args=(net_recv, net_send, config),
        daemon=True  # Hintergrundprozess für Nachrichtenversand und -empfang
    )
    net_proc.start()

    # 3) CLI-User-Interface im Hauptprozess ausführen:
    #    Führt run_ui aus, welche Eingaben verarbeitet und mit den Pipes kommuniziert.
    try:
        run_ui(net_cmd, net_evt, disc_cmd, disc_evt, config)
    except KeyboardInterrupt:
        # Behandelt Strg-C sauber: bricht die UI-Schleife ab und fährt Prozesse herunter
        print("\n[System] Abbruch per Strg-C.")
    finally:
        # Sichere Beendigung: Alle Daemon-Prozesse beenden und auf Join warten
        net_proc.terminate()
        disc_proc.terminate()
        net_proc.join()
        disc_proc.join()

if __name__ == "__main__":
    main()
