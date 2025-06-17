# ui.py – Kommandozeilen-Interface mit config edit & Bildbetrachter

import threading
import sys
import time
import subprocess
from colorama import init, Fore
from config import Config

init(autoreset=True)

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config):
    """
    @brief Startet die CLI: msg, img, who, leave, quit, config.
    """
    handle = config.handle

    # 1) TCP-Port abwarten
    print("Starte Network-Service, warte auf TCP-Port …")
    while True:
        evt = pipe_net_evt.recv()
        if evt[0] == "tcp_port":
            tcp_port = evt[1]
            break

    # 2) JOIN + WHO
    pipe_disc_cmd.send(("join", handle, tcp_port))
    time.sleep(0.1)
    pipe_disc_cmd.send(("who",))

    known_peers = {}
    last_printed = {}
    stop_event = threading.Event()

    def disc_listener():
        nonlocal known_peers, last_printed
        while not stop_event.is_set():
            evt = pipe_disc_evt.recv()
            if evt[0] == "users":
                known_peers = evt[1]
                if known_peers != last_printed:
                    last_printed = dict(known_peers)
                    print("\n[Discovery] Teilnehmer:")
                    for h,(ip,pr) in known_peers.items():
                        print(f"  {h}: {ip}:{pr}")
            elif evt[0] == "error":
                print(f"\n[Discovery Fehler] {evt[1]}")

    def net_listener():
        while not stop_event.is_set():
            evt = pipe_net_evt.recv()
            if evt[0] == "msg":
                _, sender, text = evt
                print(f"\n{sender}> {text}")
            elif evt[0] == "img":
                _, sender, path = evt
                print(f"\nBild von {sender} gespeichert: {path}")
                # Bildbetrachter öffnen
                subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif evt[0] == "error":
                print(f"\n[Network Fehler] {evt[1]}")

    threading.Thread(target=disc_listener, daemon=True).start()
    threading.Thread(target=net_listener, daemon=True).start()

    print(f"\n{Fore.LIGHTGREEN_EX}Willkommen {handle}!")
    print(f"{Fore.LIGHTYELLOW_EX}Befehle: msg, img, allmsg, who, leave, config, quit")

    while True:
        line = input(">> ").strip()
        if not line: continue
        parts = line.split(" ",1)
        cmd   = parts[0]
        rest  = parts[1] if len(parts)>1 else ""

        try:
            if cmd == "msg":
                to, text = rest.split(" ",1)
                ip,pr = known_peers[to]
                pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))

            elif cmd == "img":
                to, path = rest.split(" ",1)
                ip,pr = known_peers[to]
                pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))

            elif cmd == "allmsg":
                for to,(ip,pr) in known_peers.items():
                    if to!=handle:
                        pipe_net_cmd.send(("send_msg", handle, to, rest, ip, pr))

            elif cmd == "who":
                pipe_disc_cmd.send(("who",))
                print("\n[Discovery] manuell:")
                for h,(ip,pr) in known_peers.items():
                    print(f"  {h}: {ip}:{pr}")

            elif cmd == "leave":
                pipe_disc_cmd.send(("leave", handle))

            elif cmd == "config":
                # config edit
                print("=== Config bearbeiten ===")
                new_handle = input(f"Handle [{config.handle}]: ") or config.handle
                new_auto   = input(f"Autoreply [{config.autoreply}]: ") or config.autoreply
                config.handle   = new_handle
                config.autoreply = new_auto
                config.save()
                print("Config gespeichert.")

            elif cmd in ("quit","exit"):
                pipe_disc_cmd.send(("leave", handle))
                stop_event.set()
                sys.exit(0)

            else:
                print("Unbekannter Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")