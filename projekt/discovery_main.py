import sys
from config import Config
from discovery import run_discovery_service
from multiprocessing.connection import Listener
import os

if __name__ == "__main__":
    """
    @file discovery_main.py
    @brief Startet genau einen Discovery-Dienst pro Host/Port (Lockfile).
    """
    if len(sys.argv) < 2:
        print("Usage: python3 discovery_main.py <config.toml> [ipc_port]")
        sys.exit(1)

    config = Config(sys.argv[1])
    ipc_port = int(sys.argv[2]) if len(sys.argv) > 2 else config.whoisport
    lockfile = f"/tmp/chat_discovery_{ipc_port}.lock"

    # Singleton via Lockfile
    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        print(f"Discovery auf Port {ipc_port} läuft bereits.")
        sys.exit(1)

    address = ('localhost', ipc_port)
    with Listener(address, authkey=b'ipc_secret') as listener:
        print(f"[Discovery] IPC-Listener auf {address}")
        conn = listener.accept()
        print("[Discovery] UI verbunden, starte Service …")
        run_discovery_service(conn, conn, config)

    os.close(fd)
    os.unlink(lockfile)