# network.py – Versenden und Empfangen von Nachrichten (SLCP) über TCP/UDP

import socket
import threading
import time
from pathlib import Path

def run_network_service(pipe_cmd, pipe_evt, config):
    """
    @brief Netzwerkdienst: Empfängt und sendet SLCP-Nachrichten (MSG, IMG) per TCP und UDP.
    @param pipe_cmd Pipe für eingehende Befehle vom UI-Prozess.
    @param pipe_evt Pipe für ausgehende Ereignisse an den UI-Prozess.
    @param config Konfigurationsobjekt (Ports, Handle, Bildverzeichnis etc.).
    """
    handle = config.handle
    image_dir = Path(config.imagepath)
    image_dir.mkdir(parents=True, exist_ok=True)

    # 1) TCP-Server auf Port binden
    tcp_srv = None
    bound = None
    for p in range(config.port_range[0], config.port_range[1] + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('', p))
            s.listen()
            tcp_srv = s
            bound = p
            break
        except OSError:
            continue

    if tcp_srv is None:
        pipe_evt.send(("error", "Kein freier TCP-Port"))
        return

    # 2) UDP-Socket für Bild-Transfer (gleicher Port)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    udp_sock.bind(('', bound))

    # Informiere UI über den gewählten TCP-Port
    pipe_evt.send(("tcp_port", bound))

    # --- Handler für eingehende TCP-Verbindungen ---
    def handle_tcp(conn):
        """
        @brief Bearbeitet eingehende TCP-Verbindungen mit SLCP-Textnachrichten.
        @param conn Aktive TCP-Verbindung (Socket).
        """
        try:
            header = b''
            while not header.endswith(b'\n'):
                c = conn.recv(1)
                if not c:
                    return
                header += c

            parts = header.decode().strip().split(" ", 2)
            cmd, sender = parts[0], parts[1] if len(parts) > 1 else ''
            if cmd == 'MSG':
                text = parts[2] if len(parts) > 2 else ''
                pipe_evt.send(("msg", sender, text))
        except Exception as e:
            pipe_evt.send(("error", f"net handle_tcp: {e}"))
        finally:
            conn.close()

    # --- TCP-Listener-Thread ---
    def tcp_listener(server_socket):
        """
        @brief Akzeptiert eingehende TCP-Verbindungen in einer Endlosschleife.
        @param server_socket Der gebundene TCP-Server-Socket.
        """
        while True:
            conn, _ = server_socket.accept()
            threading.Thread(target=handle_tcp, args=(conn,), daemon=True).start()

    threading.Thread(target=tcp_listener, args=(tcp_srv,), daemon=True).start()

    # --- UDP-Listener-Thread (Bild-Empfang) ---
    def udp_listener():
        """
        @brief Bearbeitet eingehende UDP-Pakete für Bildübertragung.
        """
        while True:
            data, addr = udp_sock.recvfrom(65535)
            if data.startswith(b"IMG"):
                header, _, rest = data.partition(b'\n')
                parts = header.decode().split()
                if len(parts) == 3:
                    _, sender, size_s = parts
                    size = int(size_s)
                    img_data = rest
                    # Lese nach, bis die gesamte Bildgröße empfangen ist
                    while len(img_data) < size:
                        chunk, _ = udp_sock.recvfrom(65535)
                        img_data += chunk
                    # Speichere das Bild ab
                    filename = image_dir / f"{sender}_{int(time.time())}.jpg"
                    with open(filename, "wb") as f:
                        f.write(img_data)
                    pipe_evt.send(("img", sender, str(filename)))

    threading.Thread(target=udp_listener, daemon=True).start()

    # --- 3) Ausgehende Befehle verarbeiten ---
    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple):
            continue
        action = cmd[0]
        try:
            if action == 'send_msg':
                _, frm, to, text, ip, port = cmd
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    s.sendall(f"MSG {frm} {text}\n".encode())

            elif action == 'send_img':
                _, frm, to, path, ip, port = cmd
                img_data = Path(path).read_bytes()
                hdr = f"IMG {frm} {len(img_data)}\n".encode()
                # Sende Header + erste Datenchunk
                udp_sock.sendto(hdr + img_data[:60000], (ip, port))
                offset = 60000
                # Sende restliche Daten in 60000-Byte-Stücken
                while offset < len(img_data):
                    udp_sock.sendto(img_data[offset:offset+60000], (ip, port))
                    offset += 60000

        except Exception as e:
            pipe_evt.send(("error", f"net send '{action}': {e}"))
