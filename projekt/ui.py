# ui.py – CLI mit automatischem JOIN+WHO und manueller Sichtbarkeit

import threading
import sys
import time
from colorama import init, Fore

init(autoreset=True)

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config):
    handle = config.handle

    # 1) Auf TCP-Port warten
    print("Starte Network-Service, warte auf TCP-Port …")
    while True:
        evt = pipe_net_evt.recv()
        if evt[0] == "tcp_port":
            tcp_port = evt[1]
            print(f"[System] Network hört auf TCP-Port {tcp_port}")
            break

    # 2) Automatisches JOIN & WHO (mit kurzer Pause)
    pipe_disc_cmd.send(("join", handle, tcp_port))
    time.sleep(0.1)
    pipe_disc_cmd.send(("who",))

    known_peers = {}
    last_printed = {}
    stop_event = threading.Event()

    # 3a) Discovery-Listener (nur bei Änderung drucken)
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
                    print("\n[Discovery] Bekannte Teilnehmer:")
                    for h,(ip,pr) in known_peers.items():
                        print(f"  {h}: {ip}:{pr}")
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
                print(f"\nNachricht von {sender}: {text}")
            elif evt[0] == "img":
                _, sender, path = evt
                print(f"\nBild von {sender} gespeichert: {path}")
            elif evt[0] == "error":
                print(f"\n[Network Fehler] {evt[1]}")

    threading.Thread(target=disc_listener, daemon=True).start()
    threading.Thread(target=net_listener,  daemon=True).start()

    print(f"\n{Fore.LIGHTGREEN_EX}Willkommen im Chat, {handle}!")
    print(f"{Fore.LIGHTYELLOW_EX}Befehle: msg <handle> <text>, img <handle> <pfad>, allmsg <text>, who, leave, quit")

    # 4) Kommando-Eingabe
    while True:
        try:
            line = input("\nEingabe: ").strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            cmd   = parts[0]
            rest  = parts[1] if len(parts) > 1 else ""

            if cmd == "msg":
                to, text = rest.split(" ", 1)
                if to in known_peers:
                    ip, pr = known_peers[to]
                    pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen!")

            elif cmd == "img":
                to, path = rest.split(" ", 1)
                if to in known_peers:
                    ip, pr = known_peers[to]
                    pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen!")

            elif cmd == "allmsg":
                for to,(ip,pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, rest, ip, pr))
                print("Nachricht an alle gesendet.")

            elif cmd == "who":
                pipe_disc_cmd.send(("who",))
                # sofort manuell ausgeben
                if known_peers:
                    print("\n[Discovery] Bekannte Teilnehmer (manuell):")
                    for h,(ip,pr) in known_peers.items():
                        print(f"  {h}: {ip}:{pr}")
                else:
                    print("\n[Discovery] Keine Bekannten Teilnehmer.")

            elif cmd == "leave":
                pipe_disc_cmd.send(("leave", handle))

            elif cmd in ("quit","exit"):
                pipe_disc_cmd.send(("leave", handle))
                print("Chat beendet.")
                stop_event.set()
                sys.exit(0)

            else:
                print("Ungültiger Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")