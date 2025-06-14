import socket
import threading
from typing import Dict, Tuple

BROADCAST_ADDR = '255.255.255.255'
BUFFER_SIZE = 4096

def _get_local_ip() -> str:
    """
    @brief Liefert die lokale IP-Adresse des aktuellen Hosts.
    @return Lokale IPv4-Adresse als String.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def run_discovery_service(pipe_cmd, pipe_evt, config) -> None:
    """
    @brief Discovery-Dienst: Verarbeitet JOIN-, WHO- und LEAVE-Nachrichten über UDP-Broadcast.
    @param pipe_cmd Pipe mit Befehlen vom UI-Prozess.
    @param pipe_evt Pipe für Rückmeldungen an UI (bekannte Nutzer).
    @param config Konfiguration mit Whois-Port und Benutzername.
    """
    whois_port = config.whoisport
    registry: Dict[str, Tuple[str, int]] = {}
    last_registry: Dict[str, Tuple[str, int]] = {}

    local_ip = _get_local_ip()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    sock.bind(('', whois_port))

    def send_update():
        nonlocal last_registry
        if registry != last_registry:
            pipe_evt.send(("users", dict(registry)))
            last_registry = dict(registry)

    def listener():
        while True:
            try:
                data, addr = sock.recvfrom(BUFFER_SIZE)
                msg = data.decode('utf-8').strip()

                if msg.startswith('JOIN'):
                    _, h, p = msg.split()
                    registry[h] = (addr[0], int(p))

                    entries = [f"{h2} {ip} {pr}" for h2, (ip, pr) in registry.items()]
                    sock.sendto(('KNOWNUSERS ' + ','.join(entries) + '\n').encode('utf-8'), addr)

                    join_msg = f"JOIN {h} {p}\n".encode('utf-8')
                    for peer_h, (peer_ip, peer_pr) in registry.items():
                        if peer_h != h:
                            sock.sendto(join_msg, (peer_ip, peer_pr))

                    send_update()

                elif msg.startswith('LEAVE'):
                    _, h = msg.split()
                    registry.pop(h, None)
                    send_update()

                elif msg == 'WHO':
                    entries = [f"{h2} {ip} {pr}" for h2, (ip, pr) in registry.items()]
                    sock.sendto(('KNOWNUSERS ' + ','.join(entries) + '\n').encode('utf-8'), addr)

                elif msg.startswith('KNOWNUSERS'):
                    rest = msg[len('KNOWNUSERS '):]
                    for entry in rest.split(','):
                        h2, ip, pr = entry.split()
                        registry[h2] = (ip, int(pr))
                    send_update()

            except Exception as e:
                pipe_evt.send(("error", f"Discovery listener: {e}"))

    threading.Thread(target=listener, daemon=True).start()

    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple) or not cmd:
            continue

        action = cmd[0]
        try:
            if action == 'join':
                _, h, p = cmd
                registry[h] = (local_ip, int(p))
                sock.sendto(f"JOIN {h} {p}\n".encode('utf-8'), (BROADCAST_ADDR, whois_port))

            elif action == 'who':
                sock.sendto(b"WHO\n", (BROADCAST_ADDR, whois_port))

            elif action == 'leave':
                _, h = cmd
                registry.pop(h, None)
                send_update()
                msg = f"LEAVE {h}\n".encode('utf-8')
                sock.sendto(msg, (BROADCAST_ADDR, whois_port))
                for _, (ip, pr) in registry.items():
                    sock.sendto(msg, (ip, pr))

        except Exception as e:
            pipe_evt.send(("error", f"Discovery command '{action}': {e}"))
