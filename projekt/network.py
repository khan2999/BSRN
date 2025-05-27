# Versenden und Empfangen von Nachrichten (SLCP)

import socket
import threading
import os

def run_network_service(pipe_recv, pipe_send, config):
    udp_port = config['port']
    autoreply = config['autoreply']
    imagepath = config['imagepath']

    if not os.path.exists(imagepath):
        os.makedirs(imagepath)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", udp_port))

    def listen():
        while True:
            data, addr = sock.recvfrom(65535)
            if data.startswith(b"MSG"):
                parts = data.decode("utf-8").split(" ", 2)
                sender = addr[0]
                print(f"\n[Nachricht von {parts[1]}]: {parts[2]}")
                pipe_send.send(("msg", parts[1], parts[2]))

            elif data.startswith(b"IMG"):
                parts = data.decode("utf-8").split(" ")
                size = int(parts[2])
                img_data, _ = sock.recvfrom(size)
                filename = os.path.join(imagepath, f"bild_von_{parts[1]}.jpg")
                with open(filename, "wb") as f:
                    f.write(img_data)
                print(f"\n[Empfangenes Bild gespeichert: {filename}]")
                pipe_send.send(("img", parts[1], filename))

    threading.Thread(target=listen, daemon=True).start()

    while True:
        if pipe_recv.poll():
            cmd, *args = pipe_recv.recv()

            if cmd == "send_msg":
                handle, text, ip, port = args
                message = f"MSG {handle} {text}".encode("utf-8")
                sock.sendto(message, (ip, port))

            elif cmd == "send_img":
                handle, path, ip, port = args
                with open(path, "rb") as f:
                    img_data = f.read()
                size = len(img_data)
                header = f"IMG {handle} {size}".encode("utf-8")
                sock.sendto(header, (ip, port))
                sock.sendto(img_data, (ip, port))