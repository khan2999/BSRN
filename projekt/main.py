# main.py

import multiprocessing
import sys
from ui import run_ui
from discovery import run_discovery_service
from network import run_network_service
from config import load_config

def main():
    # Konfigurationsdatei als Argument übergeben
    if len(sys.argv) < 2:
        print("⚠️  Bitte gib den Pfad zur TOML-Datei an. Beispiel:\n   python main.py config_bob.toml")
        return
    config_path = sys.argv[1]
    config = load_config(config_path)

    # Pipes für Kommunikation
    ui_to_net, net_from_ui = multiprocessing.Pipe()
    ui_to_disc, disc_from_ui = multiprocessing.Pipe()
    net_to_ui, ui_from_net = multiprocessing.Pipe()
    disc_to_ui, ui_from_disc = multiprocessing.Pipe()

    # 3 Prozesse starten
    ui_process = multiprocessing.Process(
        target=run_ui,
        args=(net_from_ui, net_to_ui, disc_from_ui, disc_to_ui, config)
    )

    network_process = multiprocessing.Process(
        target=run_network_service,
        args=(ui_to_net, net_to_ui, config)
    )

    discovery_process = multiprocessing.Process(
        target=run_discovery_service,
        args=(ui_to_disc, disc_to_ui, config)
    )

    # Prozesse starten
    ui_process.start()
    network_process.start()
    discovery_process.start()

    # Auf Beendigung der UI warten
    ui_process.join()

    # Netzwerk- und Discovery-Prozesse beenden
    network_process.terminate()
    discovery_process.terminate()

if __name__ == '__main__':
    main()
