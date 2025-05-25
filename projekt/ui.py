# Kommandozeilenoberfläche

def run_ui(pipe_net_out, pipe_net_in, pipe_disc_out, pipe_disc_in, config):
    handle = config['handle']

    print(f"Willkommen im Chat, {handle}!")
    print("Befehle: MSG <handle> <text>, IMG <handle> <pfad>, WHO, LEAVE, QUIT")

    known_users = {}

    while True:
        if pipe_disc_in.poll():
            msg_type, data = pipe_disc_in.recv()
            if msg_type == "users":
                known_users = data
                print("\nBekannte Teilnehmer:")
                for h, (ip, port) in known_users.items():
                    print(f"  {h}: {ip}:{port}")

        if pipe_net_in.poll():
            msg_type, sender, content = pipe_net_in.recv()
            if msg_type == "MSG":
                print(f"\nNachricht von {sender}: {content}")
            elif msg_type == "IMG":
                print(f"\nBild von {sender} gespeichert unter: {content}")

        try:
            cmd = input("\n> ").strip().split(" ", 2)
            if not cmd:
                continue

            if cmd[0] == "MSG" and len(cmd) == 3:
                to, text = cmd[1], cmd[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_msg", to, text, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'WHO' ausführen.")

            elif cmd[0] == "IMG" and len(cmd) == 3:
                to, path = cmd[1], cmd[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_img", to, path, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'WHO' ausführen.")

            elif cmd[0] == "WHO":
                pipe_disc_out.send("WHO")

            elif cmd[0] == "LEAVE":
                pipe_disc_out.send("LEAVE")

            elif cmd[0] == "QUIT":
                pipe_disc_out.send("LEAVE")
                break

            else:
                print("Ungültiger Befehl.")

        except EOFError:
            print("\n[System] Eingabe beendet. Beende Chat.")
            pipe_disc_out.send("LEAVE")
            break

        except Exception as e:
            print(f"Fehler: {e}")
