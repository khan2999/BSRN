# ui.py – Kommandozeilen-Interface mit config edit, Bildbetrachter und farbiger Handle-Anzeige

import threading
import sys
import time
import subprocess
from itertools import cycle
from colorama import init, Fore, Style
from config import Config

init(autoreset=True)

# Standard-Farben für Handles, falls in TOML keine Farbe definiert
_COLOR_CYCLE = cycle([
    Fore.RED, Fore.GREEN, Fore.YELLOW,
    Fore.BLUE, Fore.MAGENTA, Fore.CYAN
])

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config: Config):
    """
    @brief Startet das CLI: msg, img, allmsg, who, leave, config, quit
    @param pipe_net_cmd Pipe zu Network-Service für ausgehende Befehle
    @param pipe_net_evt Pipe von Network-Service für Events
    @param pipe_disc_cmd Pipe zu Discovery-Service für ausgehende Befehle
    @param pipe_disc_evt Pipe von Discovery-Service für Events
    @param config Config-Objekt mit handle, autoreply, imagepath, handle_colors
    """
    handle = config.handle

    # Map Handle → ANSI-Farbe
    handle_to_color: dict[str, str] = {}

    def get_color(h: str) -> str:
        if h in handle_to_color:
            return handle_to_color[h]
        # 1) Farbe aus TOML-Sektion [colors]
        name = config.handle_colors.get(h, "").upper()
        if hasattr(Fore, name):
            col = getattr(Fore, name)
        else:
            # 2) Fallback: zyklische Standard-Farbe
            col = next(_COLOR_CYCLE)
        handle_to_color[h] = col
        return col

    # 1) Auf TCP-Port warten
    print("Starte Network-Service, warte auf TCP-Port …")
    while True:
        evt = pipe_net_evt.recv()
        if evt[0] == "tcp_port":
            tcp_port = evt[1]
            print(f"[System] Network hört auf TCP-Port {tcp_port}")
            break

    # 2) Automatisches JOIN & WHO mit kurzer Pause
    pipe_disc_cmd.send(("join", handle, tcp_port))
    time.sleep(0.1)
    pipe_disc_cmd.send(("who",))

    known_peers = {}
    last_printed = {}
    stop_event = threading.Event()

    # 3a) Discovery-Listener
    def disc_listener():
        nonlocal known_peers, last_printed
        while not stop_event.is_set():
            try:
                evt = pipe_disc_evt.recv()
            except (EOFError, OSError):
                break

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

    # 3b) Network-Listener
    def net_listener():
        while not stop_event.is_set():
            try:
                evt = pipe_net_evt.recv()
            except (EOFError, OSError):
                break

            if evt[0] == "msg":
                _, sender, text = evt
                col = get_color(sender)
                print(f"\n{col}{sender}{Style.RESET_ALL}> {text}")

            elif evt[0] == "img":
                _, sender, path = evt
                col = get_color(sender)
                print(f"\nBild von {col}{sender}{Style.RESET_ALL} gespeichert: {path}")
                # Bildbetrachter öffnen
                subprocess.Popen(
                    ['xdg-open', path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            elif evt[0] == "error":
                print(f"\n[Network Fehler] {evt[1]}")

    threading.Thread(target=disc_listener, daemon=True).start()
    threading.Thread(target=net_listener,  daemon=True).start()

    # Begrüßung
    print(f"\n{Fore.LIGHTGREEN_EX}Willkommen {handle}!{Style.RESET_ALL}")
    print(
        f"{Fore.LIGHTYELLOW_EX}"
        "Befehle: msg <handle> <text>, img <handle> <datei-pfad>, allmsg <text>, "
        "who, leave, config, quit"
        f"{Style.RESET_ALL}"
    )

    # 4) Kommando-Eingabe
    while True:
        try:
            line = input("\nEingabe: ").strip()
            if not line:
                continue

            parts = line.split(" ", 1)
            cmd = parts[0]
            rest = parts[1] if len(parts) > 1 else ""

            if cmd == "msg":
                to, text = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))

            elif cmd == "img":
                to, path = rest.split(" ", 1)
                ip, pr = known_peers[to]
                pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))

            elif cmd == "allmsg":
                for to, (ip, pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, rest, ip, pr))

            elif cmd == "who":
                pipe_disc_cmd.send(("who",))
                print("\n[Discovery] manuell:")
                for h, (ip, pr) in known_peers.items():
                    col = get_color(h)
                    print(f"  {col}{h}{Style.RESET_ALL}: {ip}:{pr}")

            elif cmd == "leave":
                pipe_disc_cmd.send(("leave", handle))

            elif cmd == "config":
                # config edit
                print("=== Config bearbeiten ===")
                new_handle = input(f"Handle [{config.handle}]: ") or config.handle
                new_auto = input(f"Autoreply [{config.autoreply}]: ") or config.autoreply
                config.handle = new_handle
                config.autoreply = new_auto
                config.save()
                print("Config gespeichert.")

            elif cmd in ("quit", "exit"):
                pipe_disc_cmd.send(("leave", handle))
                stop_event.set()
                sys.exit(0)

            else:
                print("Unbekannter Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")