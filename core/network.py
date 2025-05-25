import socket
import threading

BUFFER_SIZE = 1024
BROADCAST_IP = "255.255.255.255"
BROADCAST_PORT = 4000

# === JOIN ===
def send_join(handle: str, port: int):
    message = f"JOIN {handle} {port}\n".encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(message, ("127.0.0.1", 4000))
        print(f"[INFO] JOIN gesendet: {message.decode().strip()}")

# === WHOIS ===
def send_whois(target_handle: str):
    message = f"WHOIS {target_handle}\n".encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(message, (BROADCAST_IP, BROADCAST_PORT))
        print(f"[INFO] WHOIS gesendet: {message.decode().strip()}")

# === MSG ===
def send_msg(target_ip: str, target_port: int, sender_handle: str, text: str):
    message = f"MSG {sender_handle} {text}\n".encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(message, (target_ip, target_port))
        print(f"[INFO] Nachricht gesendet an {target_ip}:{target_port}")

# === UDP-Listener ===
def start_udp_listener(local_port: int, own_handle: str):
    def listener():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("", local_port))
            print(f"[INFO] UDP-Listener läuft auf Port {local_port}...")
            while True:
                data, addr = s.recvfrom(BUFFER_SIZE)
                handle_incoming_message(data, addr, own_handle, local_port)

    threading.Thread(target=listener, daemon=True).start()

# === Discovery-Listener (für WHOIS) ===
def start_discovery_listener(own_handle: str, own_port: int):
    def listener():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", BROADCAST_PORT))
            print("[INFO] Discovery-Listener läuft auf Port 4000...")
            while True:
                data, addr = s.recvfrom(BUFFER_SIZE)
                handle_incoming_message(data, addr, own_handle, own_port)

    threading.Thread(target=listener, daemon=True).start()

# === Verarbeitung eingehender Nachrichten ===
def handle_incoming_message(data: bytes, addr, own_handle: str, own_port: int):
    try:
        print(f"[DEBUG] Nachricht angekommen – handle_incoming_message für: {own_handle}")
        message = data.decode().strip()
        print(f"[RECV] {addr} → {message}")
        parts = message.split()
        if not parts:
            return
        command = parts[0]

        if command == "WHOIS" and len(parts) == 2:
            target = parts[1]
            print(f"[DEBUG] WHOIS erhalten: {target}, ich heiße: {own_handle}")
            if target.lower() == own_handle.lower():
                ip = addr[0]
                reply = f"IAM {own_handle} {ip} {own_port}\n".encode("utf-8")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.sendto(reply, addr)
                    print(f"[INFO] IAM gesendet: {reply.decode().strip()}")

        elif command == "IAM" and len(parts) == 4:
            print(f"[INFO] Teilnehmer gefunden: {message.strip()}")

        elif command == "MSG" and len(parts) >= 3:
            sender = parts[1]
            msg_text = " ".join(parts[2:])
            print(f"[MSG] {sender}: {msg_text}")

    except Exception as e:
        print(f"[ERROR] Fehler beim Verarbeiten der Nachricht: {e}")
