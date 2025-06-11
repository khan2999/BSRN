# main.py

import sys
import multiprocessing
import time

from config import Config
from discovery import run_discovery_service
from network   import run_network_service
from ui        import run_ui

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 main.py <alice.toml|bob.toml>")
        sys.exit(1)

    config = Config(sys.argv[1])

    # Pipes anlegen
    net_cmd, net_recv   = multiprocessing.Pipe()
    net_send, net_evt   = multiprocessing.Pipe()
    disc_cmd, disc_recv = multiprocessing.Pipe()
    disc_send, disc_evt = multiprocessing.Pipe()

    # 1) Discovery-Prozess starten
    disc_proc = multiprocessing.Process(
        target=run_discovery_service,
        args=(disc_recv, disc_send, config),
        daemon=True
    )
    disc_proc.start()

    # Kurze Pause, damit Discovery bereits lauscht
    time.sleep(0.1)

    # 2) Network-Prozess starten
    net_proc = multiprocessing.Process(
        target=run_network_service,
        args=(net_recv, net_send, config),
        daemon=True
    )
    net_proc.start()

    # 3) UI im Hauptprozess
    try:
        run_ui(net_cmd, net_evt, disc_cmd, disc_evt, config)
    except KeyboardInterrupt:
        print("\n[System] Abbruch per Strg-C.")
    finally:
        net_proc.terminate()
        disc_proc.terminate()
        net_proc.join()
        disc_proc.join()

if __name__ == "__main__":
    main()
