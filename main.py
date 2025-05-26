import sys
from core.config_loader import load_config
from core.network import (
    send_join,
    send_leave,
    start_udp_listener,
    start_discovery_listener,
    send_whois,
    send_msg,
)

def main():
    if len(sys.argv) < 2:
        print("⚠️ Bitte gib den Pfad zur Konfigurationsdatei an, z. B.:")
        print("   python3 main.py config/alice.toml")
        return

    config_path = sys.argv[1]
    config = load_config(config_path)
    handle = config["handle"]
    port = config["port"]

    # UDP Listener starten
    start_udp_listener(port, handle)
    start_discovery_listener(handle, port)

    print(f"🟢 Chat-Client ({handle}) gestartet.")
    print(
        "Verfügbare Befehle: JOIN | WHOIS <Handle> | MSG <IP>:<Port> <Nachricht> | LEAVE | EXIT")

    while True:
        try:
            command = input("> ").strip()
            if command == "JOIN":
                send_join(handle, port)
            elif command.startswith("WHOIS "):
                target = command.split(" ", 1)[1]
                send_whois(target)
            elif command.startswith("MSG "):
                try:
                    rest = command[4:]
                    addr_str, text = rest.split(" ", 1)
                    ip, port_str = addr_str.split(":")
                    target_port = int(port_str)
                    send_msg(ip, target_port, handle, text)
                except Exception as e:
                    print(f"[Fehler] Ungültiger MSG-Befehl: {e}")
            elif command.upper() == "LEAVE":
                send_leave(handle)
            elif command == "EXIT":
                print("👋 Chat-Client wird beendet.")
                break
            else:
                print("[WARNUNG] Unbekannter Befehl.")
        except KeyboardInterrupt:
            print("\n[INFO] Manuell beendet.")
            break

if __name__ == "__main__":
    main()
