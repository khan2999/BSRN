# discovery.py – Broadcast-basiertes Teilnehmer-Discovery

import socket
import threading
from typing import Dict, Tuple

BROADCAST_ADDR = '255.255.255.255'
BUFFER_SIZE    = 4096

def _get_local_ip() -> str:
    """
    @brief Ermittelt lokale IP-Adresse (für JOIN).
    @return lokale IP als String.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except:
        return '127.0.0.1'
    finally:
        s.close()

def run_discovery_service(pipe_cmd, pipe_evt, config) -> None:
    """
    @brief Hauptfunktion des Discovery-Dienstes.
    @param pipe_cmd Pipe von UI → Discovery (JOIN, WHO, LEAVE).
    @param pipe_evt Pipe von Discovery → UI (users, error).
    @param config Config-Objekt mit whoisport.
    """
    whois_port = config.whoisport
    registry: Dict[str, Tuple[str,int]] = {}
    last_registry: Dict[str, Tuple[str,int]] = {}

    local_ip = _get_local_ip()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except:
        pass
    sock.bind(('', whois_port))

    def send_update_if_changed():
        nonlocal last_registry
        if registry != last_registry:
            pipe_evt.send(("users", dict(registry)))
            last_registry = dict(registry)

    def listener():
        nonlocal last_registry
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            msg = data.decode('utf-8').strip()

            if msg.startswith('JOIN'):
                _, h, p = msg.split()
                registry[h] = (addr[0], int(p))
                entries = [f"{h2} {ip} {pr}" for h2,(ip,pr) in registry.items()]
                full_msg = ('KNOWNUSERS ' + ','.join(entries) + '\n').encode()
                sock.sendto(full_msg, (BROADCAST_ADDR, whois_port))
                send_update_if_changed()

            elif msg.startswith('LEAVE'):
                _, h = msg.split()
                registry.pop(h, None)
                send_update_if_changed()

            elif msg == 'WHO':
                entries = [f"{h2} {ip} {pr}" for h2,(ip,pr) in registry.items()]
                sock.sendto(('KNOWNUSERS ' + ','.join(entries) + '\n').encode(), addr)
                pipe_evt.send(("users", dict(registry)))
                last_registry = dict(registry)

            elif msg.startswith('KNOWNUSERS'):
                rest = msg[len('KNOWNUSERS '):]
                for entry in rest.split(','):
                    h2, ip, pr = entry.split()
                    registry[h2] = (ip, int(pr))
                pipe_evt.send(("users", dict(registry)))
                last_registry = dict(registry)

    threading.Thread(target=listener, daemon=True).start()

    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple): continue
        action = cmd[0]
        if action == 'join':
            _, h, p = cmd
            registry[h] = (local_ip, int(p))
            send_update_if_changed()
            sock.sendto(f"JOIN {h} {p}\n".encode(),
                        (BROADCAST_ADDR, whois_port))

        elif action == 'who':
            sock.sendto(b"WHO\n", (BROADCAST_ADDR, whois_port))
            pipe_evt.send(("users", dict(registry)))
            last_registry = dict(registry)

        elif action == 'leave':
            _, h = cmd
            registry.pop(h, None)
            send_update_if_changed()
            sock.sendto(f"LEAVE {h}\n".encode(),
                        (BROADCAST_ADDR, whois_port))