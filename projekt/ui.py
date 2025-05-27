# Kommandozeilenoberfläche

def run_ui(pipe_net_out, pipe_net_in, pipe_disc_out, pipe_disc_in, config):
    handle = config['handle']

    # Begrüßung und Command Liste
    print(f"Willkommen im Chat, {handle}!")
    print("Befehle: msg <handle> <text>, img <handle> <pfad>, who, leave, quit")

    # Dictionary für bekannte Teilnehmer im Chat
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
            if msg_type == "msg":
                print(f"\nNachricht von {sender}: {content}")
            elif msg_type == "img":
                print(f"\nBild von {sender} gespeichert unter: {content}")

        try:
            cmd = input("\n> ").strip().split(" ", 2)
            if not cmd:
                continue

            # Nachricht senden
            if cmd[0] == "msg" and len(cmd) == 3:
                to, text = cmd[1], cmd[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_msg", to, text, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            # Bild senden
            elif cmd[0] == "img" and len(cmd) == 3:
                to, path = cmd[1], cmd[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_img", to, path, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            # Liste der aktiven Nutzer
            elif cmd[0] == "who":
                pipe_disc_out.send("who")

            # Chatraum verlassen
            elif cmd[0] == "leave":
                pipe_disc_out.send("leave")

            # Programm beenden
            elif cmd[0] == "quit":
                pipe_disc_out.send("leave")
                break

            else:
                print("Ungültiger Befehl.")

        except EOFError:
            print("\n[System] Eingabe beendet. Beende Chat.")
            pipe_disc_out.send("leave")
            break

        except Exception as e:
            print(f"Fehler: {e}")
