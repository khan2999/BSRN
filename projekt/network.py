# network.py

import socket
import os

def run_network_service(pipe_recv, pipe_send, config):
    port = config['port']
    imagepath = config['imagepath']
    os.makedirs(imagepath, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port))

    def send_msg(to, text, ip, port):
        message = f"MSG {to} {text}".encode('utf-8')
        sock.sendto(message, (ip, port))

    def send_img(to, filepath, ip, port):
        try:
            size = os.path.getsize(filepath)
            header = f"IMG {to} {size}".encode('utf-8')
            sock.sendto(header, (ip, port))
            with open(filepath, 'rb') as f:
                sock.sendto(f.read(), (ip, port))
        except Exception as e:
            print(f"Fehler beim Senden des Bildes: {e}")

    from threading import Thread

    def listener():
        while True:
            data, addr = sock.recvfrom(65536)
            try:
                decoded = data.decode('utf-8')
                if decoded.startswith("MSG"):
                    _, sender, text = decoded.split(" ", 2)
                    pipe_send.send(("msg", sender, text))

                elif decoded.startswith("IMG"):
                    _, sender, size = decoded.split()
                    size = int(size)
                    image_data, _ = sock.recvfrom(size)
                    filename = os.path.join(imagepath, f"{sender}_bild.jpg")
                    with open(filename, 'wb') as f:
                        f.write(image_data)
                    pipe_send.send(("img", sender, filename))

            except UnicodeDecodeError:
                continue

    Thread(target=listener, daemon=True).start()

    while True:
        if pipe_recv.poll():
            cmd = pipe_recv.recv()
            if cmd[0] == "send_msg":
                _, to, text, ip, port = cmd
                send_msg(to, text, ip, port)
            elif cmd[0] == "send_img":
                _, to, path, ip, port = cmd
                send_img(to, path, ip, port)
