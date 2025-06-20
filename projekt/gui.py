# @file chat_client_gui.py
# @brief Erweiterte grafische Chat-Oberfläche mit AFK-Modus, Broadcast-Funktion und Bildanzeige.
# @details Diese GUI-Anwendung ermöglicht Text- und Bildkommunikation über ein Netzwerk mit
# Discovery-Mechanismus. Zusätzlich unterstützt sie Abwesenheitsmeldungen (AFK),
# Broadcasts und eine Join/Leave-Logik zur Teilnehmerverwaltung.

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import multiprocessing
import time
import sys
import os
from config import Config
from discovery import run_discovery_service
from network import run_network_service
from PIL import Image, ImageTk

class ChatClientGUI:
    """
    @class ChatClientGUI
    @brief Hauptklasse der GUI-Anwendung mit Abwesenheitsmodus und erweiterten Chatfunktionen.
    """
    def __init__(self, config_path: str):
        self.load_config(config_path)
        self.afk_mode = False
        self.autoreply_text = getattr(self.config, "autoreply", "Ich bin gerade nicht erreichbar.")
        self._setup_services()
        self._build_gui()
        self._start_listeners()
        self._auto_join()
        self.chat_images = []  # Referenzen für angezeigte Bilder
        self.root.mainloop()

    def load_config(self, config_path: str) -> None:
        self.config = Config(config_path)
        self.handle = self.config.handle
        raw = getattr(self.config, 'handle_colors', {})
        self.handle_colors = {h.lower(): c for h, c in raw.items()}

    def _setup_services(self) -> None:
        self.net_cmd, net_recv = multiprocessing.Pipe()
        net_send, self.net_evt = multiprocessing.Pipe()
        self.disc_cmd, disc_recv = multiprocessing.Pipe()
        disc_send, self.disc_evt = multiprocessing.Pipe()

        self.disc_proc = multiprocessing.Process(
            target=run_discovery_service,
            args=(disc_recv, disc_send, self.config),
            daemon=True
        )
        self.disc_proc.start()
        time.sleep(0.1)

        self.net_proc = multiprocessing.Process(
            target=run_network_service,
            args=(net_recv, net_send, self.config),
            daemon=True
        )
        self.net_proc.start()

    def _build_gui(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"Chat-Client: {self.handle}")
        self._create_menu()
        self._create_widgets()
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.display_message("System", f"Willkommen {self.handle}!")

    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Konfig laden", command=self._open_config_dialog)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.on_close)
        menubar.add_cascade(label="Datei", menu=filemenu)
        self.root.config(menu=menubar)

    def _create_widgets(self) -> None:
        # Teilnehmerliste
        self.peers = {}
        self.peer_list = ttk.Treeview(self.root, columns=("ip","port","name"), show="headings")
        self.peer_list.heading("ip", text="IP-Adresse")
        self.peer_list.heading("port", text="Port")
        self.peer_list.heading("name", text="Name")
        self.peer_list.column("ip", width=120)
        self.peer_list.column("port", width=60)
        self.peer_list.column("name", width=100)
        self.peer_list.grid(row=0, column=0, rowspan=3, sticky="nswe", padx=5, pady=5)
        self.peer_list.bind('<<TreeviewSelect>>', self.on_peer_select)
        for tag, color in self.handle_colors.items():
            try:
                self.peer_list.tag_configure(tag, foreground=color)
            except Exception:
                pass

        # Chat-Anzeige
        self.chat_display = scrolledtext.ScrolledText(self.root, state=tk.DISABLED)
        self.chat_display.grid(row=0, column=1, columnspan=2, sticky="nswe", padx=5, pady=5)
        for tag, color in self.handle_colors.items():
            try:
                self.chat_display.tag_configure(tag, foreground=color)
            except Exception:
                pass

        # Eingabefeld & Buttons
        self.entry_text = tk.Entry(self.root)
        self.entry_text.grid(row=1, column=1, sticky="we", padx=5)
        self.send_btn = tk.Button(self.root, text="Senden", command=self.send_message)
        self.send_btn.grid(row=1, column=2, sticky="we", padx=5)
        self.img_btn = tk.Button(self.root, text="Bild senden", command=self.send_image)
        self.img_btn.grid(row=2, column=1, columnspan=2, sticky="we", padx=5)

        # Join/Leave-Button
        self.in_chat = True
        self.chat_toggle_btn = tk.Button(self.root, text="Leave", command=self.toggle_chat_status)
        self.chat_toggle_btn.grid(row=4, column=0, sticky="we", padx=5, pady=5)

        # Quit-Button
        self.quit_btn = tk.Button(self.root, text="Quit", command=self.on_close)
        self.quit_btn.grid(row=4, column=2, sticky="we", padx=5, pady=5)

        # Label für ausgewählten Nutzer
        self.selected_label = tk.Label(self.root, text="Ausgewählter Nutzer: --", anchor='w')
        self.selected_label.grid(row=3, column=0, columnspan=3, sticky="we", padx=5, pady=2)

        # Broadcast-Button
        self.broadcast_btn = tk.Button(self.root, text="An alle senden", command=self.send_broadcast_message)
        self.broadcast_btn.grid(row=1, column=0, rowspan=2, sticky="nswe", padx=5, pady=5)

        # AFK/Abwesenheit
        self.afk_btn = tk.Button(self.root, text="Abwesenheits-Modus", command=self.toggle_afk)
        self.afk_btn.grid(row=4, column=1, sticky="we", padx=5, pady=5)

    def toggle_chat_status(self) -> None:
        """
        @brief Ermöglicht das manuelle Verlassen und Wiederbeitreten zum Chat.
        @details Aktualisiert GUI und informiert andere Teilnehmer.
        """
        if self.in_chat:
            try:
                self.disc_cmd.send(("leave", self.handle))
                self.display_message("System", "Du hast den Chat verlassen.")
                for h, (ip, port) in self.peers.items():
                    if h != self.handle:
                        self.net_cmd.send(("send_msg", "System", h,
                                           f"{self.handle} hat den Chat verlassen.", ip, port))
            except Exception:
                pass
            self.entry_text.config(state=tk.DISABLED)
            self.send_btn.config(state=tk.DISABLED)
            self.img_btn.config(state=tk.DISABLED)
            self.chat_toggle_btn.config(text="Join")
            self.in_chat = False
        else:
            try:
                self.disc_cmd.send(("join", self.handle, self.config.port_range[0]))
                self.display_message("System", "Du bist dem Chat beigetreten.")
                for h, (ip, port) in self.peers.items():
                    if h != self.handle:
                        self.net_cmd.send(("send_msg", "System", h,
                                           f"{self.handle} ist dem Chat beigetreten.", ip, port))
            except Exception:
                pass
            self.entry_text.config(state=tk.NORMAL)
            self.send_btn.config(state=tk.NORMAL)
            self.img_btn.config(state=tk.NORMAL)
            self.chat_toggle_btn.config(text="Leave")
            self.in_chat = True

    def toggle_afk(self) -> None:
        """
        @brief Aktiviert oder deaktiviert den Abwesenheitsmodus (AFK).
        """
        self.afk_mode = not self.afk_mode
        state = "aktiviert" if self.afk_mode else "deaktiviert"
        self.display_message("System", f"Abwesenheits-Modus {state}.")
        self.afk_btn.config(text="Abwesenheits-Modus" if not self.afk_mode else "Zurück (Anwesend)")

    def on_peer_select(self, event) -> None:
        
        """
        @brief Aktualisiert die Anzeige des ausgewählten Chatpartners in der GUI.
        """
        sel = self.peer_list.selection()
        if sel:
            name = sel[0]
            color = self.handle_colors.get(name.lower(), 'black')
            self.selected_label.config(text=f"Ausgewählter Nutzer: {name}", fg=color)
        else:
            self.selected_label.config(text="Ausgewählter Nutzer: --", fg='black')

    def _start_listeners(self) -> None:
        """
        @brief Startet Hintergrund-Threads für Netzwerk- und Discovery-Events.
        """
        self.stop_event = threading.Event()
        threading.Thread(target=self.disc_listener, daemon=True).start()
        threading.Thread(target=self.net_listener, daemon=True).start()

    def _auto_join(self) -> None:
        """
        @brief Automatischer Beitritt zum Netzwerk beim Start.
        """
        self.disc_cmd.send(("join", self.handle, self.config.port_range[0]))
        time.sleep(0.1)
        self.disc_cmd.send(("who",))

    def _open_config_dialog(self) -> None:
        """
        @brief Öffnet Dialog zur Auswahl einer neuen TOML-Konfigurationsdatei.
        @details Startet die Anwendung neu mit der gewählten Konfiguration.
        """
        path = filedialog.askopenfilename(
            title="Konfigurationsdatei wählen",
            filetypes=[("TOML-Dateien","*.toml")],
            initialdir=os.path.join(os.getcwd(),'config')
        )
        if path:
            messagebox.showinfo("Neustart nötig","App wird neu gestartet.")
            self.on_close()
            os.execv(sys.executable, [sys.executable, __file__, path])

    def disc_listener(self) -> None:
        """
        @brief Reagiert auf Änderungen der Discovery-Teilnehmerliste.
        """
        last = {}
        while not self.stop_event.is_set():
            evt = self.disc_evt.recv()
            if evt[0] == "users":
                users = evt[1]
                if users != last:
                    last = users.copy()
                    self.peers = users
                    self.update_peer_list()

    def net_listener(self) -> None:
        """
        @brief Verarbeitet eingehende Nachrichten, Bilder oder Netzwerkfehler.
        @details Antwortet bei aktivem AFK-Modus automatisch auf eingehende Nachrichten.
        """
        while not self.stop_event.is_set():
            evt = self.net_evt.recv()
            if evt[0] == "msg":
                _, sender, text = evt
                if sender != self.handle:
                    if self.afk_mode:
                        ip, port = self.peers.get(sender, (None, None))
                        if ip and port:
                            self.net_cmd.send(("send_msg", self.handle, sender, self.autoreply_text, ip, port))
                        # Nachricht wird nicht angezeigt
                    else:
                        self.display_message(sender, text)
            elif evt[0] == "img":
                _, sender, path = evt
                if sender != self.handle:
                    self.display_image(sender, path)
            elif evt[0] == "error":
                messagebox.showerror("Network-Fehler", evt[1])

    def update_peer_list(self) -> None:
        """
        @brief Aktualisiert die Peer-Anzeige in der GUI.
        """
        for item in self.peer_list.get_children():
            self.peer_list.delete(item)
        for h, (ip, pr) in self.peers.items():
            tag = h.lower() if h.lower() in self.handle_colors else None
            tags = (tag,) if tag else ()
            self.peer_list.insert("", tk.END, iid=h, values=(ip, pr, h), tags=tags)

    def display_message(self, sender: str, text: str) -> None:
        """
        @brief Zeigt eine Textnachricht im Chatfenster an.
        @param sender Name des Absenders.
        @param text Inhalt der Nachricht.
        """
        self.chat_display.config(state=tk.NORMAL)
        tag = sender.lower() if sender.lower() in self.handle_colors else None
        if tag:
            self.chat_display.insert(tk.END, f"{sender}: {text}\n", tag)
        else:
            self.chat_display.insert(tk.END, f"{sender}: {text}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def display_image(self, sender: str, image_path: str) -> None:
        """
        @brief Zeigt ein Bild im Chatfenster an.
        @param sender Name des Absenders.
        @param image_path Dateipfad des empfangenen Bildes.
        """
        try:
            img = Image.open(image_path)
            max_width = 200
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.chat_images.append(photo)

            self.chat_display.config(state=tk.NORMAL)
            tag = sender.lower() if sender.lower() in self.handle_colors else None
            if tag:
                self.chat_display.insert(tk.END, f"{sender}: ", tag)
            else:
                self.chat_display.insert(tk.END, f"{sender}: ")
            self.chat_display.image_create(tk.END, image=photo)
            self.chat_display.insert(tk.END, "\n")
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Bildfehler", f"Bild konnte nicht angezeigt werden: {e}")

    def send_message(self) -> None:
        """
        @brief Sendet eine Textnachricht an den aktuell ausgewählten Peer.
        """
        sel = self.peer_list.selection()
        if not sel:
            messagebox.showwarning("Keine Auswahl","Bitte Empfänger auswählen.")
            return
        target = sel[0]
        text = self.entry_text.get().strip()
        if not text:
            return
        ip, port = self.peers[target]
        self.net_cmd.send(("send_msg", self.handle, target, text, ip, port))
        self.display_message(self.handle, text)
        self.entry_text.delete(0, tk.END)

    def send_broadcast_message(self) -> None:
        """
        @brief Sendet eine Nachricht an alle bekannten Peers.
        """
        text = self.entry_text.get().strip()
        if not text:
            return
        for target, (ip, port) in self.peers.items():
            if target != self.handle:
                self.net_cmd.send(("send_msg", self.handle, target, text, ip, port))
        self.display_message(self.handle, f"[an alle] {text}")
        self.entry_text.delete(0, tk.END)

    def send_image(self) -> None:
        """
        @brief Sendet ein Bild an den aktuell ausgewählten Peer.
        """
        sel = self.peer_list.selection()
        if not sel:
            messagebox.showwarning("Keine Auswahl","Bitte Empfänger auswählen.")
            return
        target = sel[0]
        path = filedialog.askopenfilename(
            title="Bild auswählen",
            filetypes=[("JPEG","*.jpg;*.jpeg"),("PNG","*.png"),("Alle","*")]
        )
        if not path:
            return
        ip, port = self.peers[target]
        self.net_cmd.send(("send_img", self.handle, target, path, ip, port))
        self.display_image(self.handle, path)

    def on_close(self) -> None:
        """
        @brief Beendet die Anwendung und informiert die Peers über das Verlassen.
        """
        try:
            self.disc_cmd.send(("leave", self.handle))
            for h, (ip, port) in self.peers.items():
                if h != self.handle:
                    self.net_cmd.send(
                        ("send_msg", "System", h,
                         f"{self.handle} hat den Chat verlassen (Programm beendet).", ip, port)
                    )
            time.sleep(0.2)
        except Exception:
            pass
        self.stop_event.set()
        self.net_proc.terminate()
        self.disc_proc.terminate()
        self.root.destroy()

def start_gui(config_path: str) -> None:
    """
    @fn start_gui
    @brief Startet die GUI-Anwendung mit gegebener Konfiguration.
    @param config_path Pfad zur TOML-Konfigurationsdatei.
    """
    ChatClientGUI(config_path)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        root = tk.Tk(); root.withdraw()
        cfg = filedialog.askopenfilename(
            title="Konfig auswählen",
            filetypes=[("TOML","*.toml")],
            initialdir=os.path.join(os.getcwd(),'config')
        )
        root.destroy()
        if not cfg:
            print("Keine Konfig ausgewählt.")
            sys.exit(1)
        sys.argv.append(cfg)
    start_gui(sys.argv[1])