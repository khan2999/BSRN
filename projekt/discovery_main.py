import sys
from config import Config
from discovery import run_discovery_service
from multiprocessing.connection import Listener

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 discovery_main.py <configfile.toml> [ipc_port]")
        sys.exit(1)

    config = Config(sys.argv[1])
    ipc_port = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    address = ('localhost', ipc_port)

    with Listener(address, authkey=b'ipc_secret') as listener:
        print(f"[Discovery] IPC-Listener läuft auf {address}")
        conn = listener.accept()
        print("[Discovery] UI verbunden, starte Service …")
        run_discovery_service(conn, conn, config)
