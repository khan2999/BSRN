
# discovery.py – Broadcast-basiertes Teilnehmer-Discovery

import socket
import threading

BROADCAST_ADDR = '255.255.255.255'
BUFFER_SIZE = 1024

def run_discovery_service(pipe_recv, pipe_send, config):
    """
    Startet den Discovery-Service:
      - Sendet einen JOIN-Broadcast
      - Lauscht auf JOIN, LEAVE, WHO und KNOWNUSERS
      - Pflegt eine Liste bekannter Nutzer und sendet Updates via pipe_send
    """
    whoisport    = config['whoisport']
    local_handle = config['handle']
    local_port   = config['port']
    user_registry = {}  # handle -> (ip, port)

    # 1) Socket anlegen und konfigurieren
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        # SO_REUSEPORT ist nicht überall verfügbar
        pass
    sock.bind(('', whoisport))

    # 2) Listener-Thread: verarbeitet eingehende Pakete
    def listener():
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            msg = data.decode('utf-8').strip()

            if msg.startswith('JOIN'):
                _, handle, port = msg.split()
                user_registry[handle] = (addr[0], int(port))

            elif msg.startswith('LEAVE'):
                _, handle = msg.split()
                user_registry.pop(handle, None)

            elif msg.startswith('WHO'):
                # jemand fragt nach aktuellen Nutzern
                response = 'KNOWNUSERS ' + ','.join(
                    f"{h} {ip} {p}"
                    for h, (ip, p) in user_registry.items()
                )
                sock.sendto(response.encode('utf-8'), addr)

            elif msg.startswith('KNOWNUSERS'):
                # Update der lokalen Nutzerliste
                entries = msg[len('KNOWNUSERS '):].split(',')
                for entry in entries:
                    h, ip, p = entry.strip().split()
                    user_registry[h] = (ip, int(p))
                # Informiere Hauptprozess über neue Liste
                pipe_send.send(("users", dict(user_registry)))

    threading.Thread(target=listener, daemon=True).start()

    # 3) JOIN-Broadcast senden (einmalig beim Start)
    join_msg = f"JOIN {local_handle} {local_port}".encode('utf-8')
    sock.sendto(join_msg, (BROADCAST_ADDR, whoisport))

    # 4) Hauptschleife: verarbeitet Befehle von main.py (über pipe_recv)
    while True:
        cmd = pipe_recv.recv()
        if cmd == 'leave':
            leave_msg = f"LEAVE {local_handle}".encode('utf-8')
            # Broadcast LEAVE
            sock.sendto(leave_msg, (BROADCAST_ADDR, whoisport))
            # optional: alle bekannten direkt benachrichtigen
            for _, (ip, p) in user_registry.items():
                sock.sendto(leave_msg, (ip, p))

        elif cmd == 'who':
            # Broadcast WHO
            sock.sendto(b"WHO", (BROADCAST_ADDR, whoisport))
