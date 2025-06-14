import sys
from config import Config
from network import run_network_service
from multiprocessing.connection import Listener

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 network_main.py <configfile.toml> [ipc_port]")
        sys.exit(1)

    config = Config(sys.argv[1])
    ipc_port = int(sys.argv[2]) if len(sys.argv) > 2 else 6001
    address = ('localhost', ipc_port)

    with Listener(address, authkey=b'ipc_secret') as listener:
        print(f"[Network] IPC-Listener läuft auf {address}")
        conn = listener.accept()
        print("[Network] UI verbunden, starte Service …")
        run_network_service(conn, conn, config)
