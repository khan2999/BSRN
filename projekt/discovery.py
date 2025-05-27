# discovery.py – Broadcast-basiertes Teilnehmer-Discovery

import socket
import threading

BROADCAST_ADDR = '255.255.255.255'
user_registry = {}  # handle: (ip, port)

def run_discovery_service(pipe_recv, pipe_send, config):
    whoisport = config['whoisport']
    local_handle = config['handle']
    local_port = config['port']

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', whoisport))

    def listener():
        while True:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8')

            if msg.startswith('JOIN'):
                _, handle, port = msg.split()
                user_registry[handle] = (addr[0], int(port))

            elif msg.startswith('LEAVE'):
                _, handle = msg.split()
                user_registry.pop(handle, None)

            elif msg.startswith('WHO'):
                response = 'KNOWNUSERS ' + ', '.join([
                    f"{h} {ip} {p}" for h, (ip, p) in user_registry.items()
                ])
                sock.sendto(response.encode('utf-8'), addr)

            elif msg.startswith('KNOWNUSERS'):
                known = msg[len('KNOWNUSERS '):]
                users = known.split(', ')
                for u in users:
                    handle, ip, port = u.split()
                    user_registry[handle] = (ip, int(port))
                pipe_send.send(("users", user_registry))

    threading.Thread(target=listener, daemon=True).start()

    # JOIN senden (Broadcast)
    join_msg = f"JOIN {local_handle} {local_port}".encode('utf-8')
    sock.sendto(join_msg, (BROADCAST_ADDR, whoisport))

    while True:
        if pipe_recv.poll():
            cmd = pipe_recv.recv()
            if cmd == "leave":
                leave_msg = f"LEAVE {local_handle}".encode('utf-8')
                sock.sendto(leave_msg, (BROADCAST_ADDR, whoisport))
                for handle, (ip, port) in user_registry.items():
                    sock.sendto(leave_msg, (ip, port))
            elif cmd == "who":
                sock.sendto(b"WHO", (BROADCAST_ADDR, whoisport))
