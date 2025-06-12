# network.py – Versenden und Empfangen von Nachrichten (SLCP) über TCP

import socket
import threading
import time
from pathlib import Path


def run_network_service(pipe_cmd, pipe_evt, config):
    """
    pipe_cmd: UI → Network
      - ("send_msg", from_handle, to_handle, text, ip, port)
      - ("send_img", from_handle, to_handle, filepath, ip, port)
    pipe_evt: Network → UI
      - ("tcp_port", bound_port)
      - ("msg", sender, text)
      - ("img", sender, saved_filepath)
      - ("error", str)
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

    # Informiere UI über den Port
    pipe_evt.send(("tcp_port", bound))

    # Handler für eingehende TCP-Verbindungen (Text-Nachrichten)
    def handle_tcp(conn):
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

    # TCP-Listener-Thread
    def tcp_listener():
        while True:
            conn, _ = tcp_srv.accept()
            threading.Thread(target=handle_tcp, args=(conn,), daemon=True).start()

    threading.Thread(target=tcp_listener, daemon=True).start()

    # UDP-Listener-Thread (Bild-Empfang)
    def udp_listener():
        while True:
            data, addr = udp_sock.recvfrom(65535)
            if data.startswith(b"IMG"):
                header, _, rest = data.partition(b'\n')
                parts = header.decode().split()
                if len(parts) == 3:
                    _, sender, size_s = parts
                    size = int(size_s)
                    img_data = rest
                    while len(img_data) < size:
                        chunk, _ = udp_sock.recvfrom(65535)
                        img_data += chunk
                    filename = image_dir / f"{sender}_{int(time.time())}.jpg"
                    with open(filename, "wb") as f:
                        f.write(img_data)
                    pipe_evt.send(("img", sender, str(filename)))

    threading.Thread(target=udp_listener, daemon=True).start()

    # 3) Ausgehende Befehle
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
                udp_sock.sendto(hdr + img_data[:60000], (ip, port))
                offset = 60000
                while offset < len(img_data):
                    udp_sock.sendto(img_data[offset:offset+60000], (ip, port))
                    offset += 60000

        except Exception as e:
            pipe_evt.send(("error", f"net send '{action}': {e}"))