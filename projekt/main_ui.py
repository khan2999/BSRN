import sys
from config import Config
from ui import run_ui
from multiprocessing.connection import Client

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 main_ui.py <configfile.toml> [disc_port] [net_port]")
        sys.exit(1)

    config = Config(sys.argv[1])
    disc_port = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    net_port  = int(sys.argv[3]) if len(sys.argv) > 3 else 6001

    disc_addr = ('localhost', disc_port)
    disc_conn = Client(disc_addr, authkey=b'ipc_secret')
    print(f"[UI] Mit Discovery verbunden an {disc_addr}")

    net_addr  = ('localhost', net_port)
    net_conn  = Client(net_addr, authkey=b'ipc_secret')
    print(f"[UI] Mit Network verbunden an {net_addr}")

    run_ui(net_conn, net_conn, disc_conn, disc_conn, config)
