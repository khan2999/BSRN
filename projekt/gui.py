"""
 * @brief Grafische Oberfläche für den Chat-Client unter Verwendung von tkinter.
 * @details Startet Discovery- und Network-Dienste in Hintergrundprozessen,
 *          zeigt Teilnehmerliste und Nachrichtenfenster an,
 *          ermöglicht Versenden von Textnachrichten und Bildern.
"""

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

class ChatClientGUI:
    """
    @brief Hauptklasse der GUI-Anwendung.
    """
    def __init__(self, config_path: str):
        """
        @brief Konstruktor: Initialisiert GUI, Pipes und Prozesse.
        @param[in] config_path Pfad zur TOML-Konfigurationsdatei.
        """
        self.load_config(config_path)
        self._setup_services()
        self._build_gui()
        self._start_listeners()
        self._auto_join()
        self.root.mainloop()

    def load_config(self, config_path: str) -> None:
        """
        @brief Lädt die Konfiguration aus einer TOML-Datei.
        """
        self.config = Config(config_path)
        self.handle = self.config.handle
        raw = getattr(self.config, 'handle_colors', {})
        # keys auf lowercase normalisieren
        self.handle_colors = {h.lower(): c for h, c in raw.items()}

    def _setup_services(self) -> None:
        """
        @brief Initialisiert Pipes und startet Discovery- und Network-Prozesse.
        """
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
        """
        @brief Setzt alle GUI-Komponenten auf, inklusive Farbcodierung.
        """
        self.root = tk.Tk()
        self.root.title(f"Chat-Client: {self.handle}")
        self._create_menu()
        self._create_widgets()
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Konfig laden", command=self._open_config_dialog)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.on_close)
        menubar.add_cascade(label="Datei", menu=filemenu)
        self.root.config(menu=menubar)

    def _create_widgets(self) -> None:
        """
        @brief Erstellt Teilnehmerliste, Chat-Display, Eingabefelder und Selektionsanzeige.
        """
        # Teilnehmerliste
        self.peers = {}
        self.peer_list = ttk.Treeview(self.root, columns=("ip","port"), show="headings")
        self.peer_list.heading("ip", text="IP-Adresse")
        self.peer_list.heading("port", text="Port")
        self.peer_list.grid(row=0, column=0, rowspan=3, sticky="nswe", padx=5, pady=5)
        self.peer_list.bind('<<TreeviewSelect>>', self.on_peer_select)

        # Chat-Anzeige
        self.chat_display = scrolledtext.ScrolledText(self.root, state=tk.DISABLED)
        self.chat_display.grid(row=0, column=1, columnspan=2, sticky="nswe", padx=5, pady=5)

        # Selektionsanzeige unter Peer-Liste
        self.selected_label = tk.Label(self.root, text="Ausgewählter Peer: --", anchor='w')
        self.selected_label.grid(row=3, column=0, columnspan=3, sticky="we", padx=5, pady=2)

        # Farb-Tags für Peer-Liste
        for tag, color in self.handle_colors.items():
            try:
                self.peer_list.tag_configure(tag, foreground=color)
            except Exception:
                pass

        # Farb-Tags für Chat-Nachrichten
        for tag, color in self.handle_colors.items():
            try:
                self.chat_display.tag_configure(tag, foreground=color)
            except Exception:
                pass

        # Eingabe und Buttons
        self.entry_text = tk.Entry(self.root)
        self.entry_text.grid(row=4, column=1, sticky="we", padx=5)
        self.send_btn = tk.Button(self.root, text="Senden", command=self.send_message)
        self.send_btn.grid(row=4, column=2, sticky="we", padx=5)
        self.img_btn = tk.Button(self.root, text="Bild senden", command=self.send_image)
        self.img_btn.grid(row=5, column=1, columnspan=2, sticky="we", padx=5)

    def on_peer_select(self, event) -> None:
        """
        @brief Aktualisiert das Label mit ausgewähltem Peer und Farbe.
        """
        sel = self.peer_list.selection()
        if sel:
            name = sel[0]
            color = self.handle_colors.get(name.lower(), 'black')
            self.selected_label.config(text=f"Ausgewählter Peer: {name}", fg=color)
        else:
            self.selected_label.config(text="Ausgewählter Peer: --", fg='black')

    def _start_listeners(self) -> None:
        self.stop_event = threading.Event()
        threading.Thread(target=self.disc_listener, daemon=True).start()
        threading.Thread(target=self.net_listener, daemon=True).start()

    def _auto_join(self) -> None:
        self.disc_cmd.send(("join", self.handle, self.config.port_range[0]))
        time.sleep(0.1)
        self.disc_cmd.send(("who",))

    def _open_config_dialog(self) -> None:
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
        while not self.stop_event.is_set():
            evt = self.net_evt.recv()
            if evt[0] == "msg":
                _, sender, text = evt
                if sender == self.handle:
                    continue
                self.display_message(sender, text)
            elif evt[0] == "img":
                _, sender, path = evt
                if sender == self.handle:
                    continue
                self.display_message(sender, f"<Bild gespeichert: {path}>")
            elif evt[0] == "error":
                messagebox.showerror("Network-Fehler", evt[1])

    def update_peer_list(self) -> None:
        for item in self.peer_list.get_children():
            self.peer_list.delete(item)
        for h, (ip, pr) in self.peers.items():
            tag = h.lower() if h.lower() in self.handle_colors else None
            tags = (tag,) if tag else ()
            self.peer_list.insert("", tk.END, iid=h, values=(ip, pr), tags=tags)

    def display_message(self, sender: str, text: str) -> None:
        """
        @brief Fügt eine neue Zeile im Chat-Display hinzu, gefärbt nach Handle.
        @param[in] sender Handle des Absenders.
        @param[in] text   Inhalt der Nachricht.
        """
        self.chat_display.config(state=tk.NORMAL)
        tag = sender.lower() if sender.lower() in self.handle_colors else None
        if tag:
            self.chat_display.insert(tk.END, f"{sender}: {text}\n", tag)
        else:
            self.chat_display.insert(tk.END, f"{sender}: {text}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def send_message(self) -> None:
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

    def send_image(self) -> None:
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
        self.display_message(self.handle, f"<Bild gesendet: {path}>")

    def on_close(self) -> None:
        try:
            self.disc_cmd.send(("leave", self.handle))
        except Exception:
            pass
        self.stop_event.set()
        self.net_proc.terminate()
        self.disc_proc.terminate()
        self.root.destroy()


def start_gui(config_path: str) -> None:
    """
    @brief Hilfsfunktion zum Programmstart der GUI.
    @param[in] config_path Pfad zur TOML-Datei.
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