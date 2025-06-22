##
# @file ui.py
# @brief Kommandozeilen-Oberfläche (CLI) des dezentralen Chat-Programms.
# @details Dieses Modul bietet eine textbasierte Benutzerschnittstelle zur Steuerung
#          des Chat-Clients. Es unterstützt das Senden von Text- und Bildnachrichten,
#          Teilnehmerverwaltung via Discovery-Dienst, sowie eine manuell aktivierbare
#          Autoreply-Funktion bei Abwesenheit.
#
# Verwendet ANSI-Farben zur Anzeige und bietet Konfigurationsänderungen zur Laufzeit.
#
# @author Gruppe A11
# @date 2025

import subprocess
import sys
import threading
import time
from itertools import cycle

from colorama import Fore, Style, init

from config import Config

# ANSI-Farbcode-Ausgabe initialisieren
init(autoreset=True)

# Zyklische Standardfarben als Fallback in User interface
_COLOR_CYCLE = cycle([
    Fore.RED, Fore.GREEN, Fore.YELLOW,
    Fore.BLUE, Fore.MAGENTA, Fore.CYAN
])

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config):
    """
    @brief Startet die Kommandozeilen-Oberfläche (UI) des Chatprogramms.
    @param pipe_net_cmd Pipe zur Übermittlung von Befehlen an den Netzwerkdienst.
    @param pipe_net_evt Pipe für eingehende Netzwerkereignisse (z. B. empfangene Nachrichten).
    @param pipe_disc_cmd Pipe zur Steuerung des Discovery-Dienstes (JOIN, WHO, LEAVE).
    @param pipe_disc_evt Pipe für Discovery-Ereignisse (z. B. neue Nutzerliste).
    @param config Das geladene Konfigurationsobjekt (handle, autoreply, ports, Farben).
    """
    handle = config.handle               # aktueller Benutzername
    autoreply_enabled = False            # Autoreply startet deaktiviert
    responded_peers: set[str] = set()    # merkt, wem wir bereits autoreplyt haben

    # Mapping Handle → ANSI-Farbe
    handle_to_color: dict[str, str] = {}
    def get_color(h: str) -> str:
        """
         @brief Gibt eine ANSI-Farbe für ein gegebenes Handle zurück.
         @param h Benutzername/Handle
         @return ANSI-Farbcode (z. B. Fore.RED)
        """
        if h in handle_to_color:
            return handle_to_color[h]
        name = config.handle_colors.get(h, "").upper()
        if hasattr(Fore, name):
            col = getattr(Fore, name)
        else:
            col = next(_COLOR_CYCLE)
        handle_to_color[h] = col
        return col

    # 1) Auf TCP-Port vom Network-Service warten
    print("Starte Network-Service, warte auf TCP-Port …")
    while True:
        evt = pipe_net_evt.recv()
        if evt[0] == "tcp_port":
            tcp_port = evt[1]
            break

    # 2) Automatisches JOIN + WHO beim Start
    pipe_disc_cmd.send(("join", handle, tcp_port))
    time.sleep(0.1)
    pipe_disc_cmd.send(("who",))

    known_peers = {}      # aktuell bekannte Teilnehmer
    last_printed = {}     # zuletzt gezeigte Teilnehmerliste
    stop_event = threading.Event()

    # --- Discovery-Listener ---
    def disc_listener():
        """
        @brief Hört auf Discovery-Ereignisse und aktualisiert die bekannte Teilnehmerliste.
        @details Gibt neue oder veränderte Teilnehmer farblich auf der Konsole aus.
        """
        nonlocal known_peers, last_printed
        while not stop_event.is_set():
            evt = pipe_disc_evt.recv()
            if evt[0] == "users":
                known_peers = evt[1]
                if known_peers != last_printed:
                    last_printed = dict(known_peers)
                    print("\n[Discovery] Teilnehmer:")
                    for h, (ip, pr) in known_peers.items():
                        col = get_color(h)
                        print(f"  {col}{h}{Style.RESET_ALL}: {ip}:{pr}")
            elif evt[0] == "error":
                print(f"\n[Discovery Fehler] {evt[1]}")

    # --- Network-Listener mit bedingtem Autoreply ---
    def net_listener():
        """
        @brief Hört auf Netzwerkereignisse wie empfangene Nachrichten oder Bilder.
        @details Sendet optional Autoreply bei aktivierter Abwesenheit.
        """
        while not stop_event.is_set():
            evt = pipe_net_evt.recv()
            if evt[0] == "error":
                print(f"\n[Network Fehler] {evt[1]}\n")

            elif evt[0] == "img":
                _, sender, path = evt
                col = get_color(sender)
                print(f"\nBild von {col}{sender}{Style.RESET_ALL} gespeichert: {path}")
                subprocess.Popen(
                    ['xdg-open', path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            elif evt[0] == "msg":
                _, sender, text = evt
                col = get_color(sender)
                print(f"\n{col}{sender}{Style.RESET_ALL}> {text}")
                # Autoreply nur, wenn:
                # - manuell eingeschaltet (autoreply_enabled)
                # - Autoreply-Text gesetzt
                # - Nachricht ≠ Autoreply-Text
                # - Sender ≠ wir selbst
                # - Noch nicht geantwortet
                if (autoreply_enabled
                        and config.autoreply
                        and text != config.autoreply
                        and sender != handle
                        and sender not in responded_peers):
                    peer = known_peers.get(sender)
                    if peer:
                        ip, pr = peer
                        pipe_net_cmd.send((
                            "send_msg", handle, sender,
                            config.autoreply, ip, pr
                        ))
                        responded_peers.add(sender)

    threading.Thread(target=disc_listener, daemon=True).start()
    threading.Thread(target=net_listener, daemon=True).start()

    # Begrüßung in Grün und Befehlsübersicht in Gelb
    print(f"\n{Fore.GREEN}Willkommen im Chat, {handle}!{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Befehle: allmsg, autoreply, config, exit, img, join, leave, msg, who{Style.RESET_ALL}")

    # --- Haupt-Loop zur Verarbeitung von CLI-Kommandos ---
    while True:
        line = input("Eingabe: ").strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        cmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "allmsg":
                for to, (ip, pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, rest, ip, pr))

            elif cmd == "autoreply":
                # Manuelles Ein-/Ausschalten der Autoreply-Funktion
                autoreply_enabled = not autoreply_enabled
                state = "aktiviert" if autoreply_enabled else "deaktiviert"
                print(f"Autoreply wurde {state}.")

            elif cmd == "config":
                print("=== Config bearbeiten ===")
                old_handle = handle
                new_handle = input(f"Handle [{config.handle}]: ") or config.handle
                new_auto   = input(f"Autoreply [{config.autoreply}]: ") or config.autoreply
                # LEAVE für alten Handle
                pipe_disc_cmd.send(("leave", old_handle))
                # Config-Objekt und lokale Variable anpassen
                config.handle    = new_handle
                config.autoreply = new_auto
                config.save()
                handle = new_handle
                print("Config gespeichert.")
                # JOIN mit neuem Handle + WHO
                pipe_disc_cmd.send(("join", handle, tcp_port))
                pipe_disc_cmd.send(("who",))
                print(f"[System] Handle geändert: {old_handle} → {handle}")

            elif cmd == "exit" or cmd == "quit":
                pipe_disc_cmd.send(("leave", handle))
                print("Chat beendet.")
                stop_event.set()
                sys.exit(0)

            elif cmd == "img":
                to, path = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))

            elif cmd == "join":
                pipe_disc_cmd.send(("join", handle, tcp_port))
                pipe_disc_cmd.send(("who",))
                print("[System] Neuer JOIN gesendet.")

            elif cmd == "leave":
                pipe_disc_cmd.send(("leave", handle))
                print("Chat verlassen.")

            elif cmd == "msg":
                to, text = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))

            elif cmd == "who":
                pipe_disc_cmd.send(("who",))
                print("\n[Discovery] Bekannte Teilnehmer (manuell):")
                for h, (ip, pr) in known_peers.items():
                    col = get_color(h)
                    print(f"  {col}{h}{Style.RESET_ALL}: {ip}:{pr}")

            else:
                print("Unbekannter Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")