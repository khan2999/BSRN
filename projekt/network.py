## @file network.py
## @brief Netzwerkdienst: SLCP-Nachrichten (MSG, IMG) über TCP/UDP senden und empfangen.
##
## Dieses Modul implementiert sowohl den TCP-Server (für Textnachrichten)
## als auch den UDP-Server (für Bilddaten) und stellt Funktionen zum
## Versenden von MSG- und IMG-Nachrichten bereit.

import socket
import threading
import time
from pathlib import Path


def _tcp_listener(server_socket, handler):
    """
    @brief Akzeptiert eingehende TCP-Verbindungen und übergibt sie an den Handler.
    @param server_socket Gebundener Server-Socket (IPv4/IPv6).
    @param handler Funktion, die eine einzelne Verbindung verarbeitet.
    """
    while True:
        conn, _ = server_socket.accept()
        threading.Thread(
            target=handler,
            args=(conn,),
            daemon=True
        ).start()


def _udp_listener(udp_sock, pipe_evt, image_dir):
    """
    @brief Empfängt SLCP IMG-Nachrichten per UDP, speichert Bilder und schickt Events.
    @param udp_sock Gebundener UDP-Socket für Bilddaten.
    @param pipe_evt Pipe zum UI-Prozess für das Event "img".
    @param image_dir Verzeichnis, in dem empfangene Bilder abgelegt werden.
    """
    while True:
        data, addr = udp_sock.recvfrom(65535)
        if not data.startswith(b"IMG"):
            continue

        header, _, rest = data.partition(b"\n")
        parts = header.decode().split()
        if len(parts) != 3:
            continue

        _, sender, size_s = parts
        total_size = int(size_s)
        img_data = rest
        while len(img_data) < total_size:
            chunk, _ = udp_sock.recvfrom(65535)
            img_data += chunk

        filename = image_dir / f"{sender}_{int(time.time())}.jpg"
        with open(filename, "wb") as f:
            f.write(img_data)

        pipe_evt.send(("img", sender, str(filename)))


def run_network_service(pipe_cmd, pipe_evt, config, handle_tcp=None):
    """
    @brief Netzwerkdienst: Empfängt und sendet SLCP-Nachrichten (MSG, IMG) per TCP und UDP.
    @param pipe_cmd Pipe für eingehende Befehle vom UI-Prozess.
    @param pipe_evt Pipe für ausgehende Ereignisse an den UI-Prozess.
    @param config Konfigurationsobjekt mit Port-Range, Handle, Bildpfad etc.
    """
    handle = config.handle
    image_dir = Path(config.imagepath)
    image_dir.mkdir(parents=True, exist_ok=True)

    # 1) TCP-Server mit IPv6 & IPv4 binding
    tcp_srv = None
    bound_port = None
    for port in range(config.port_range[0], config.port_range[1] + 1):
        for family, addr in ((socket.AF_INET6, '::'), (socket.AF_INET, '')):
            try:
                srv = socket.socket(family, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, 'SO_REUSEPORT'):
                    try:
                        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except OSError:
                        pass

                bind_args = (addr, port, 0, 0) if family == socket.AF_INET6 else (addr, port)
                srv.bind(bind_args)
                srv.listen()
                tcp_srv = srv
                bound_port = port
                break
            except OSError:
                continue
        if tcp_srv:
            break

    if not tcp_srv:
        pipe_evt.send(("error", "Kein freier TCP-Port gefunden"))
        return

    # 2) UDP-Socket für Bild-Transfer (gleicher Port)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    udp_sock.bind(('', bound_port))

    # Informiere UI über den gewählten TCP-Port
    pipe_evt.send(("tcp_port", bound_port))

    # Listener-Threads starten
    threading.Thread(
        target=lambda: _tcp_listener(tcp_srv, handle_tcp),
        daemon=True
    ).start()
    threading.Thread(
        target=lambda: _udp_listener(udp_sock, pipe_evt, image_dir),
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
                    ip, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
                )
                sent = False
                for af, socktype, proto, _, sockaddr in addr_info:
                    try:
                        with socket.socket(af, socktype, proto) as sock:
                            sock.settimeout(5)
                            sock.connect(sockaddr)
                            sock.sendall(f"MSG {frm} {text}\n".encode())
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
                header = f"IMG {frm} {len(img_data)}\n".encode()
                udp_sock.sendto(header + img_data[:60000], (ip, port))
                offset = 60000
                while offset < len(img_data):
                    udp_sock.sendto(
                        img_data[offset:offset+60000],
                        (ip, port)
                    )
                    offset += 60000

        except Exception as e:
            pipe_evt.send(("error", f"net send '{action}': {e}"))