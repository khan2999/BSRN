# test_whois_sender.py
import socket

msg = "WHOIS Bob\n".encode("utf-8")
target = ("127.0.0.1", 4000)

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.sendto(msg, target)
    print("[TEST] WHOIS gesendet an localhost:4000")
