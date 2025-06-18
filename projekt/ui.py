# ui.py – Kommandozeilen-Interface mit config edit & Bildbetrachter

import threading
import sys
import time
import subprocess
from itertools import cycle
from colorama import init, Fore, Style
from config import Config

# ANSI-Farbcodes initialisieren (Windows/Linux/macOS)
init(autoreset=True)

# Standardfarben-Rotation für Handles ohne TOML-Definition
_COLOR_CYCLE = cycle([
    Fore.RED, Fore.GREEN, Fore.YELLOW,
    Fore.BLUE, Fore.MAGENTA, Fore.CYAN
])

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config):
    """
    @brief Startet die Kommandozeilen-Oberfläche (UI) des Chatprogramms.
    @param pipe_net_cmd Pipe zur Übermittlung von Befehlen an den Netzwerkdienst.
    @param pipe_net_evt Pipe für eingehende Netzwerkereignisse.
    @param pipe_disc_cmd Pipe zur Steuerung des Discovery-Dienstes.
    @param pipe_disc_evt Pipe für Discovery-Antworten.
    @param config Konfiguration mit Handle, Autoreply, Bildpfad usw.
    """
    handle = config.handle

    # Map Handle → ANSI-Farbe
    handle_to_color: dict[str, str] = {}
    def get_color(h: str) -> str:
        if h in handle_to_color:
            return handle_to_color[h]
        # 1) Farbe aus [colors] in TOML
        name = config.handle_colors.get(h, "").upper()
        if hasattr(Fore, name):
            col = getattr(Fore, name)
        else:
            # 2) Fallback: zyklische Standardfarbe
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

    # 2) Automatisches JOIN + WHO
    pipe_disc_cmd.send(("join", handle, tcp_port))
    time.sleep(0.1)
    pipe_disc_cmd.send(("who",))

    known_peers = {}      # Handle → (IP, Port)
    last_printed = {}     # zuletzt ausgegebene Teilnehmerliste
    stop_event = threading.Event()

    # Discovery-Listener: zeigt neue Teilnehmer farbig an
    def disc_listener():
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

    # Network-Listener: zeigt Text- und Bildnachrichten farbig an
    def net_listener():
        while not stop_event.is_set():
            evt = pipe_net_evt.recv()
            if evt[0] == "msg":
                _, sender, text = evt
                col = get_color(sender)
                print(f"\n{col}{sender}{Style.RESET_ALL}> {text}")
            elif evt[0] == "img":
                _, sender, path = evt
                col = get_color(sender)
                print(f"\nBild von {col}{sender}{Style.RESET_ALL} gespeichert: {path}")
                subprocess.Popen(
                    ['xdg-open', path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif evt[0] == "error":
                print(f"\n[Network Fehler] {evt[1]}")

    # Starte Listener-Threads
    threading.Thread(target=disc_listener, daemon=True).start()
    threading.Thread(target=net_listener, daemon=True).start()

    # Begrüßung immer in Grün
    print(f"\n{Fore.GREEN}Willkommen im Chat, {handle}!{Style.RESET_ALL}")
    # Befehlsübersicht in Gelb
    print(f"{Fore.YELLOW}Befehle: msg <handle> <text>, img <handle> <pfad>, allmsg <text>, who, leave, config, quit{Style.RESET_ALL}")

    # Eingabeschleife: verarbeitet CLI-Kommandos
    while True:
        line = input("Eingabe: ").strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        cmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "msg":
                # Textnachricht senden
                to, text = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))

            elif cmd == "img":
                # Bildnachricht senden
                to, path = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))

            elif cmd == "allmsg":
                # Nachricht an alle Teilnehmer (außer sich selbst)
                for to, (ip, pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, rest, ip, pr))

            elif cmd == "who":
                # Manuelle Aktualisierung der Teilnehmerliste
                pipe_disc_cmd.send(("who",))
                print("\n[Discovery] Bekannte Teilnehmer (manuell):")
                for h, (ip, pr) in known_peers.items():
                    col = get_color(h)
                    print(f"  {col}{h}{Style.RESET_ALL}: {ip}:{pr}")

            elif cmd == "leave":
                # Chat verlassen
                pipe_disc_cmd.send(("leave", handle))

            elif cmd == "config":
                # Interaktive Konfigurationsänderung
                print("=== Config bearbeiten ===")
                new_handle = input(f"Handle [{config.handle}]: ") or config.handle
                new_auto   = input(f"Autoreply [{config.autoreply}]: ") or config.autoreply
                config.handle    = new_handle
                config.autoreply = new_auto
                config.save()
                print("Config gespeichert.")

            elif cmd in ("quit", "exit"):
                # Beende Anwendung
                pipe_disc_cmd.send(("leave", handle))
                stop_event.set()
                sys.exit(0)

            else:
                print("Unbekannter Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")
