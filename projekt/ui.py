import threading
import sys
import time

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

    # 2) Automatisches JOIN & WHO
    pipe_disc_cmd.send(("join", handle, tcp_port))
    pipe_disc_cmd.send(("who",))

    known_peers = {}
    stop_event = threading.Event()

    # --- Beacon: re-announce JOIN every 5 s so late arrivals see us ---
    def join_beacon():
        while not stop_event.is_set():
            time.sleep(5)
            pipe_disc_cmd.send(("join", handle, tcp_port))

    threading.Thread(target=join_beacon, daemon=True).start()

    # 3a) Discovery-Listener-Thread
    def disc_listener():
        nonlocal known_peers
        while not stop_event.is_set():
            try:
                evt = pipe_disc_evt.recv()
            except (EOFError, OSError):
                break
            if evt[0] == "users":
                known_peers = evt[1]
                print("\n[Discovery] Bekannte Teilnehmer:")
                for h, (ip, port) in known_peers.items():
                    print(f"  {h}: {ip}:{port}")
            elif evt[0] == "error":
                print(f"\n[Discovery Fehler] {evt[1]}")

    # 3b) Network-Listener-Thread
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

    t1 = threading.Thread(target=disc_listener, daemon=True)
    t2 = threading.Thread(target=net_listener, daemon=True)
    t1.start()
    t2.start()

    # 4) Kommando-Eingabe
    print(f"\nWillkommen im Chat, {handle}!")
    print("Befehle: msg <handle> <text>, img <handle> <pfad>, allmsg <text>, who, leave, quit")

    while True:
        try:
            line = input("> ").strip()
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
                    print(f"Nachricht an {to} gesendet.")
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            elif cmd == "img":
                to, path = rest.split(" ", 1)
                if to in known_peers:
                    ip, pr = known_peers[to]
                    pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))
                    print(f"Bild an {to} gesendet.")
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            elif cmd == "allmsg":
                text = rest
                for to, (ip, pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))
                print("Nachricht an alle gesendet.")

            elif cmd == "who":
                pipe_disc_cmd.send(("who",))

            elif cmd == "leave":
                pipe_disc_cmd.send(("leave", handle))

            elif cmd in ("quit", "exit"):
                pipe_disc_cmd.send(("leave", handle))
                print("Chat beendet.")
                stop_event.set()
                t1.join(timeout=0.1)
                t2.join(timeout=0.1)
                sys.exit(0)

            else:
                print("Ungültiger Befehl.")

        except Exception as e:
            print(f"Fehler: {e}")