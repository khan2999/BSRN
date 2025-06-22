"""
@file discovery.py
@brief Discovery-Dienst für den dezentralen Chat-Client (SLCP-Protokoll).
@details Dieses Modul implementiert einen UDP-basierten Mechanismus zur automatischen
Erkennung von Teilnehmern im lokalen Netzwerk. Mithilfe von Broadcast-Nachrichten
werden Join- und Leave-Events sowie Nutzerlisten ausgetauscht.

Der Discovery-Service ist zuständig für:
- Verwaltung einer lokalen Teilnehmer-Registry
- Entgegennahme von JOIN, LEAVE, WHO-Nachrichten über UDP
- Senden von KNOWNUSERS-Antworten an andere Clients
- Synchronisation mit der UI über IPC-Pipes

Es wird ein Hintergrund-Thread verwendet, um eingehende Nachrichten parallel zur
Steuerung durch die Benutzeroberfläche (UI) zu verarbeiten.
"""



import socket
import threading
from typing import Dict, Tuple

BROADCAST_ADDR = '255.255.255.255'
BUFFER_SIZE    = 4096

def _get_local_ip() -> str:
    """
    @brief Ermittelt die lokale IP-Adresse des Hosts.
    @details Öffnet kurz ein UDP-Socket zu einem öffentlichen Server (hier Google DNS),
             um die tatsächliche Interface-IP abzurufen. Fallback auf 127.0.0.1 bei Fehler.
    @return Lokale IP-Adresse als String.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Verbindung zu externem Host, um lokale IP zu bestimmen
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        # Falls Ermittlung fehlschlägt, verwende Loopback
        return '127.0.0.1'
    finally:
        s.close()

def run_discovery_service(pipe_cmd, pipe_evt, config) -> None:
    """
    @brief Startet den Discovery-Service für Peer-to-Peer-Erkennung über UDP-Broadcast.
    @param pipe_cmd Pipe für Steuerbefehle von der UI (join, leave, who).
    @param pipe_evt Pipe zur Rückmeldung von Nutzerlisten an die UI.
    @param config Konfigurationsobjekt mit Informationen über whois-Port, Handle, usw.
    @details
    - Verwaltet eine interne Registry aller bekannten Peers im lokalen Netzwerk.
    - Reagiert auf JOIN-/LEAVE-/WHO-Anfragen.
    - Antwortet mit KNOWNUSERS-Nachrichten an andere Discovery-Instanzen.
    - Nutzt einen Listener-Thread, um UDP-Messages asynchron zu empfangen.
    """

    whois_port = config.whoisport
    registry: Dict[str, Tuple[str,int]] = {}       # aktuell erfasste Teilnehmer
    last_registry: Dict[str, Tuple[str,int]] = {}  # zuletzt gesendete Snapshot

    # Ermittele lokale IP für JOIN-Meldungen
    local_ip = _get_local_ip()

    # Erstelle UDP-Broadcast-Socket für Discovery
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Ermöglicht mehrfache Bindung unter Linux
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        # Nicht auf allen Plattformen verfügbar → ignorieren
        pass
    sock.bind(('', whois_port))

    def send_update_if_changed():
        """
    @brief Sendet eine aktualisierte Nutzerliste an die UI, falls sich die Registry geändert hat.
    @details Wird automatisch aufgerufen, wenn neue Teilnehmer erkannt oder entfernt wurden.
    Vermeidet redundante Übertragungen, indem die letzte bekannte Registry mit der aktuellen verglichen wird.
    """

        nonlocal last_registry
        if registry != last_registry:
            pipe_evt.send(("users", dict(registry)))
            last_registry = dict(registry)

    def listener():
        """
    @brief Hintergrund-Thread, der kontinuierlich eingehende UDP-Broadcasts verarbeitet.
    @details
    Erkennt und verarbeitet folgende Nachrichtenformate:
    - 'JOIN <handle> <port>' – Registrierung eines neuen Teilnehmers
    - 'LEAVE <handle>' – Abmeldung eines Teilnehmers
    - 'WHO' – Anfrage zur aktuellen Registry
    - 'KNOWNUSERS <handle ip port,...>' – Antwort auf WHO mit vollständiger Teilnehmerliste
    Nach jedem relevanten Update wird die Registry aktualisiert und ggf. an die UI gesendet.
    """

        nonlocal last_registry
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            msg = data.decode('utf-8').strip()

            if msg.startswith('JOIN'):
                # Neuer Teilnehmer tritt bei
                _, h, p = msg.split()
                registry[h] = (addr[0], int(p))
                # Verteile aktualisierte Liste per Broadcast an alle Discovery-Server
                entries = [f"{h2} {ip} {pr}" for h2,(ip,pr) in registry.items()]
                full_msg = ('KNOWNUSERS ' + ','.join(entries) + '\n').encode()
                sock.sendto(full_msg, (BROADCAST_ADDR, whois_port))
                send_update_if_changed()

            elif msg.startswith('LEAVE'):
                # Teilnehmer verlässt Chat
                _, h = msg.split()
                registry.pop(h, None)
                send_update_if_changed()

            elif msg == 'WHO':
                # Manuelle Anfrage zur Nutzerliste
                entries = [f"{h2} {ip} {pr}" for h2,(ip,pr) in registry.items()]
                sock.sendto(('KNOWNUSERS ' + ','.join(entries) + '\n').encode(), addr)
                pipe_evt.send(("users", dict(registry)))
                last_registry = dict(registry)

            elif msg.startswith('KNOWNUSERS'):
                # Antwort eines anderen Discovery-Servers sammeln
                rest = msg[len('KNOWNUSERS '):]
                for entry in rest.split(','):
                    h2, ip, pr = entry.split()
                    registry[h2] = (ip, int(pr))
                pipe_evt.send(("users", dict(registry)))
                last_registry = dict(registry)

    # Listener-Thread für eingehende Broadcasts und Unicasts starten
    threading.Thread(target=listener, daemon=True).start()

    # Verarbeite Steuerbefehle von der UI
    while True:
        cmd = pipe_cmd.recv()
        if not isinstance(cmd, tuple):
            continue
        action = cmd[0]

        if action == 'join':
            # UI fordert JOIN: lokalen Nutzer zur Registry hinzufügen und broadcasten
            _, h, p = cmd
            registry[h] = (local_ip, int(p))
            send_update_if_changed()
            sock.sendto(f"JOIN {h} {p}\n".encode(),
                        (BROADCAST_ADDR, whois_port))

        elif action == 'who':
            # UI fordert WHO: Liste aller registrierten Nutzer erfragen
            sock.sendto(b"WHO\n", (BROADCAST_ADDR, whois_port))
            pipe_evt.send(("users", dict(registry)))
            last_registry = dict(registry)

        elif action == 'leave':
            # UI fordert LEAVE: Nutzer aus Registry entfernen und Abmelde-Broadcast senden
            _, h = cmd
            registry.pop(h, None)
            send_update_if_changed()
            sock.sendto(f"LEAVE {h}\n".encode(),
                        (BROADCAST_ADDR, whois_port))
