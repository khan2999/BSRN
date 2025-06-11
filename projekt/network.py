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

    # 1) TCP-Server binden
    tcp_srv = None
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

    pipe_evt.send(("tcp_port", bound))

    def handle_conn(conn):
        try:
            header = b''
            while not header.endswith(b'\n'):
                c = conn.recv(1)
                if not c:
                    return
                header += c
            parts = header.decode('utf-8').strip().split(' ', 2)
            cmd, sender = parts[0], parts[1] if len(parts) > 1 else ''

            if cmd == 'MSG':
                text = parts[2] if len(parts) > 2 else ''
                pipe_evt.send(("msg", sender, text))

            elif cmd == 'IMG':
                size = int(parts[2]) if len(parts) > 2 else 0
                data = b''
                while len(data) < size:
                    chunk = conn.recv(size - len(data))
                    if not chunk:
                        break
                    data += chunk
                fname = image_dir / f"{sender}_{int(time.time())}.jpg"
                with open(fname, 'wb') as f:
                    f.write(data)
                pipe_evt.send(("img", sender, str(fname)))

        except Exception as e:
            pipe_evt.send(("error", f"net handle: {e}"))
        finally:
            conn.close()

    def listener():
        while True:
            conn, _ = tcp_srv.accept()
            threading.Thread(target=handle_conn, args=(conn,), daemon=True).start()

    threading.Thread(target=listener, daemon=True).start()

    # 2) Ausgehende Befehle
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
                    s.sendall(f"MSG {frm} {text}\n".encode('utf-8'))

            elif action == 'send_img':
                _, frm, to, path, ip, port = cmd
                data = Path(path).read_bytes()
                hdr = f"IMG {frm} {len(data)}\n".encode('utf-8')
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    s.sendall(hdr + data)

        except Exception as e:
            pipe_evt.send(("error", f"net send '{action}': {e}"))
