import threading
import sys
from colorama import init, Fore, Style  # Für farbigen Text

init(autoreset=True)

def run_ui(pipe_net_cmd, pipe_net_evt, pipe_disc_cmd, pipe_disc_evt, config):
    """
    @brief Startet die Kommandozeilen-Benutzerschnittstelle des Chat-Clients.
    @param pipe_net_cmd Pipe zur Kommunikation mit dem Netzwerkprozess (Befehle senden).
    @param pipe_net_evt Pipe zur Kommunikation mit dem Netzwerkprozess (Events empfangen).
    @param pipe_disc_cmd Pipe zur Kommunikation mit dem Discovery-Prozess (Befehle senden).
    @param pipe_disc_evt Pipe zur Kommunikation mit dem Discovery-Prozess (Events empfangen).
    @param config Konfigurationsobjekt mit Nutzerparametern.
    """
    handle = config.handle

    print("Starte Network-Service, warte auf TCP-Port …")
    while True:
        evt = pipe_net_evt.recv()
        if evt[0] == "tcp_port":
            tcp_port = evt[1]
            print(f"[System] Network hört auf TCP-Port {tcp_port}")
            break

    pipe_disc_cmd.send(("join", handle, tcp_port))
    pipe_disc_cmd.send(("who",))

    known_peers = {}
    stop_event = threading.Event()

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

    print(f"\n{Fore.LIGHTGREEN_EX}Willkommen im Chat, {handle}!")
    print(f"{Fore.LIGHTYELLOW_EX}Befehle: msg <handle> <text>, img <handle> <pfad>, allmsg <text>, who, leave, quit")

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
                if to in known_peers:
                    ip, pr = known_peers[to]
                    pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))
                else:
                    print("Unbekannter Nutzer. Erst 'who' Befehl ausführen!")

            elif cmd == "img":
                to, path = rest.split(" ", 1)
                if to in known_peers:
                    ip, pr = known_peers[to]
                    pipe_net_cmd.send(("send_img", handle, to, path, ip, pr))
                else:
                    print("Unbekannter Nutzer. Erst 'who' Befehl ausführen!")

            elif cmd == "allmsg":
                text = rest
                for to, (ip, pr) in known_peers.items():
                    if to != handle:
                        pipe_net_cmd.send(("send_msg", handle, to, text, ip, pr))
                print("Nachricht an alle gesendet.")

            elif cmd == "who":
                print("\n[Discovery] Bekannte Teilnehmer (manuell):")
                for h, (ip, pr) in known_peers.items():
                    print(f"  {h}: {ip}:{pr}")
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
                print("Ungültiger Befehl!")

        except Exception as e:
            print(f"Fehler: {e}")
