# main.py – Einstiegspunkt für das Chat-Programm

import multiprocessing
import os
from ui import run_ui
from discovery import run_discovery_service
from network import run_network_service
from config import load_config


def main():
    config = load_config()

    # Interprozess-Kommunikation vorbereiten
    ui_to_net, net_from_ui = multiprocessing.Pipe()
    ui_to_disc, disc_from_ui = multiprocessing.Pipe()
    net_to_ui, ui_from_net = multiprocessing.Pipe()
    disc_to_ui, ui_from_disc = multiprocessing.Pipe()

    # Prozesse starten
    discovery_process = multiprocessing.Process(
        target=run_discovery_service,
        args=(disc_from_ui, disc_to_ui, config)
    )

    network_process = multiprocessing.Process(
        target=run_network_service,
        args=(net_from_ui, net_to_ui, config)
    )

    ui_process = multiprocessing.Process(
        target=run_ui,
        args=(ui_to_net, ui_from_net, ui_to_disc, ui_from_disc, config)
    )

    discovery_process.start()
    network_process.start()
    ui_process.start()

    # Prozesse synchron beenden
    ui_process.join()
    network_process.terminate()
    discovery_process.terminate()


if __name__ == '__main__':
    main()
