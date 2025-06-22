## @file network.py
## @brief Netzwerkdienst: SLCP-Nachrichten (MSG, IMG) über TCP/UDP senden und empfangen.
##
## Dieses Modul implementiert einen TCP-Server (für Textnachrichten)
## und einen UDP-Server (für Bilddaten), die in getrennten Threads laufen.
## Es stellt Funktionen zum Empfangen und Senden von SLCP-Nachrichten bereit.

from pathlib import Path
import socket
import threading
import time

# Maximale UDP-Chunksize für Bilddaten
_CHUNK_SIZE = 60000

def _handle_tcp(conn, pipe_evt):
    """
    @brief Bearbeitet eine eingehende TCP-Verbindung für SLCP-MSG-Nachrichten.
    @param conn Socket-Objekt für die eingehende TCP-Verbindung.
    @param pipe_evt Pipe-Objekt zum Senden von Events an den UI-Prozess.
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
    @brief Wartet auf TCP-Verbindungen und startet jeweils einen neuen Thread zur Verarbeitung.
    @param server_socket Vorab gebundener TCP-Server-Socket.
    @param pipe_evt Pipe zum Senden von Events an den UI-Prozess.
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
    @brief Wartet auf UDP-Daten (SLCP-IMG), speichert empfangene Bilder und sendet Ereignisse.
    @param udp_sock Gebundener UDP-Socket für Bildempfang.
    @param pipe_evt Pipe zum Senden von Events an den UI-Prozess.
    @param image_dir Verzeichnis zur Speicherung empfangener Bilder.
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
    @brief Startet den Netzwerkdienst (TCP/UDP) und verarbeitet eingehende sowie ausgehende SLCP-Nachrichten.
    @param pipe_cmd Pipe zum Empfangen von Befehlen vom UI-Prozess.
    @param pipe_evt Pipe zum Senden von Ereignissen an den UI-Prozess.
    @param config Konfigurationsobjekt mit Attributen:
           - port_range: Tupel (min_port, max_port) zur Portauswahl,
           - handle: Benutzerkennung (Sender),
           - imagepath: Zielverzeichnis für empfangene Bilder.
    """
    handle = config.handle
    image_dir = Path(config.imagepath)
    image_dir.mkdir(parents=True, exist_ok=True)

    # TCP-Server starten
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

    # UDP-Socket auf gleichem Port binden
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    udp_sock.bind(('', bound_port))

    # Port dem UI-Prozess mitteilen
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

    # Verarbeitung ausgehender Nachrichten
    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple):
            continue
        action = cmd[0]
        try:
            if action == 'send_msg':
                """
                @brief Sendet eine SLCP-MSG-Nachricht über TCP.
                @param frm Absenderkennung.
                @param to Empfängerkennung (nicht verwendet).
                @param text Nachrichtentext.
                @param ip Ziel-IP-Adresse.
                @param port Ziel-TCP-Port.
                """
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
                """
                @brief Sendet eine SLCP-IMG-Nachricht über UDP.
                @param frm Absenderkennung.
                @param to Empfängerkennung (nicht verwendet).
                @param path Pfad zur Bilddatei.
                @param ip Ziel-IP-Adresse.
                @param port Ziel-UDP-Port.
                """
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