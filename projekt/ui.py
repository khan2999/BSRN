# ui.py – Kommandozeilenoberfläche

def run_ui(pipe_net_out, pipe_net_in, pipe_disc_out, pipe_disc_in, config):
    handle = config['handle']
    pipe_disc_out.send("who")

    print(f"Willkommen im Chat, {handle}!")
    print("Befehle: msg <handle> <text>, img <handle> <pfad>, who, allmsg <text>, leave, quit")

    known_users = {}

    while True:
        # Discovery-Updates
        if pipe_disc_in.poll():
            msg_type, data = pipe_disc_in.recv()
            if msg_type == "users":
                known_users = data
                print("\nBekannte Teilnehmer:")
                for h, (ip, port) in known_users.items():
                    print(f"  {h}: {ip}:{port}")

        # Eingehende Nachrichten / Bilder
        if pipe_net_in.poll():
            msg_type, sender, content = pipe_net_in.recv()
            if msg_type == "msg":
                print(f"\nNachricht von {sender}: {content}")
            elif msg_type == "img":
                print(f"\nBild von {sender} gespeichert unter: {content}")

        # User-Eingabe
        try:
            parts = input("\n> ").strip().split(" ", 2)
            if not parts or parts[0] == "":
                continue

            cmd = parts[0]

            if cmd == "msg" and len(parts) == 3:
                to, text = parts[1], parts[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_msg", to, text, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            elif cmd == "img" and len(parts) == 3:
                to, path = parts[1], parts[2]
                if to in known_users:
                    ip, port = known_users[to]
                    pipe_net_out.send(("send_img", to, path, ip, port))
                else:
                    print("Unbekannter Nutzer. Erst 'who' ausführen.")

            elif cmd == "allmsg" and len(parts) == 2:
                text = parts[1]
                if known_users:
                    for to, (ip, port) in known_users.items():
                        if to != handle:
                            pipe_net_out.send(("send_msg", to, text, ip, port))
                    print("Nachricht an alle gesendet.")
                else:
                    print("Keine bekannten Nutzer. Erst 'who' ausführen.")

            elif cmd == "who":
                pipe_disc_out.send("who")

            elif cmd == "leave":
                pipe_disc_out.send("leave")

            elif cmd == "quit":
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
