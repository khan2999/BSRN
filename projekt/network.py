## @file network.py
## @brief Netzwerkdienst: SLCP-Nachrichten (MSG, IMG) über TCP/UDP senden und empfangen.
##
## Dieses Modul implementiert den TCP-Server (für Textnachrichten)
## und den UDP-Server (für Bilddaten) in getrennten Threads
## und stellt Funktionen zum Versenden von MSG- und IMG-Nachrichten bereit.

from pathlib import Path
import socket
import threading
import time

# Maximale UDP-Chunksize für Bilddaten
_CHUNK_SIZE = 60000

def _handle_tcp(conn, pipe_evt):
    """
    @brief Bearbeitet eine einzelne TCP-Verbindung für SLCP-MSG.
    @param conn Aktive TCP-Verbindung (Socket).
    @param pipe_evt Pipe zum UI-Prozess.
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

def _tcp_listener(server_socket, pipe_evt):
    """
    @brief Akzeptiert eingehende TCP-Verbindungen und leitet sie weiter.
    @param server_socket Gebundener TCP-Server-Socket.
    @param pipe_evt Pipe zum UI-Prozess.
    """
    while True:
        conn, _ = server_socket.accept()
        threading.Thread(
            target=_handle_tcp,
            args=(conn, pipe_evt),
            daemon=True
        ).start()

def _udp_listener(udp_sock, pipe_evt, image_dir):
    """
    @brief Empfängt SLCP IMG-Nachrichten per UDP, speichert Bilder und sendet Events.
    @param udp_sock Gebundener UDP-Socket für Bilddaten.
    @param pipe_evt Pipe zum UI-Prozess.
    @param image_dir Verzeichnis zum Speichern der Bilder.
    """
    while True:
        data, _ = udp_sock.recvfrom(65535)
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

def run_network_service(pipe_cmd, pipe_evt, config):
    """
    @brief Netzwerkdienst: Empfängt und sendet SLCP-Nachrichten (MSG, IMG) per TCP und UDP.
    @param pipe_cmd Pipe für Befehle vom UI-Prozess.
    @param pipe_evt Pipe für Ereignisse an den UI-Prozess.
    @param config Konfigurationsobjekt mit port_range, handle und imagepath.
    """
    # Service-Setup
    handle = config.handle
    image_dir = Path(config.imagepath)
    image_dir.mkdir(parents=True, exist_ok=True)

    # 1) TCP-Server auf verfügbarem Port starten
    tcp_srv = None
    bound_port = None
    for p in range(config.port_range[0], config.port_range[1] + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('', p))
            s.listen()
            tcp_srv = s
            bound_port = p
            break
        except OSError:
            continue

    if tcp_srv is None:
        pipe_evt.send(("error", "Kein freier TCP-Port gefunden"))
        return

    # 2) UDP-Socket für Bild-Transfer auf demselben Port
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    udp_sock.bind(('', bound_port))

    # UI über gewählten TCP-Port informieren
    pipe_evt.send(("tcp_port", bound_port))

    # Listener-Threads starten
    threading.Thread(
        target=_tcp_listener,
        args=(tcp_srv, pipe_evt),
        daemon=True
    ).start()
    threading.Thread(
        target=_udp_listener,
        args=(udp_sock, pipe_evt, image_dir),
        daemon=True
    ).start()

    # 3) Ausgehende Befehle verarbeiten
    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple):
            continue
        action = cmd[0]
        try:
            if action == 'send_msg':
                _, frm, to, text, ip, port = cmd
                if len(text) > 512:
                    pipe_evt.send((
                        "error",
                        f"[SLCP] Nachricht zu lang ({len(text)} Zeichen, max. 512)"
                    ))
                    continue

                addr_info = socket.getaddrinfo(
                    ip, port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM
                )
                sent = False
                for af, socktype, proto, _, sockaddr in addr_info:
                    try:
                        with socket.socket(af, socktype, proto) as s:
                            s.settimeout(5)
                            s.connect(sockaddr)
                            s.sendall(f"MSG {frm} {text}\n".encode())
                        sent = True
                        break
                    except Exception:
                        continue

                if not sent:
                    pipe_evt.send((
                        "error",
                        f"[SLCP] Nachricht konnte nicht gesendet werden an {ip}:{port}"
                    ))

            elif action == 'send_img':
                _, frm, to, path, ip, port = cmd
                img_data = Path(path).read_bytes()
                hdr = f"IMG {frm} {len(img_data)}\n".encode()
                udp_sock.sendto(hdr + img_data[:_CHUNK_SIZE], (ip, port))
                offset = _CHUNK_SIZE
                while offset < len(img_data):
                    udp_sock.sendto(img_data[offset:offset+_CHUNK_SIZE], (ip, port))
                    offset += _CHUNK_SIZE

        except Exception as e:
            pipe_evt.send(("error", f"net send '{action}': {e}"))