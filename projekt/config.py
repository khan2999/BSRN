##
# @file config.py
# @brief Modul zur Verwaltung der TOML-basierten Konfiguration des Chat-Clients.
# @details Dieses Modul stellt die Klasse `Config` bereit, die eine Konfigurationsdatei im TOML-Format lädt, analysiert und verwaltet.
# Sie bietet Zugriff auf zentrale Parameter wie Benutzerhandle, Portbereich, Whois-Port, Autoreply-Text, Bildverzeichnis und farbliche Handle-Darstellung.
# Zusätzlich unterstützt sie das Speichern von Konfigurationsänderungen zurück in die Datei.
##
import tomllib
import toml
from pathlib import Path

class Config:
    """
    @file config.py
    @brief Lädt und speichert die TOML-Konfiguration für den Chat-Client.
    @details Legt Attribute an: `handle`, `port_range`, `whoisport`, `autoreply`, `imagepath`, `handle_colors`.
    """

    def __init__(self, path: str):
        """
        @brief Konstruktor: Initialisiert Config mit Datei-Pfad und lädt Inhalte.
        @param[in] path Pfad zur TOML-Konfigurationsdatei.
        @raises FileNotFoundError wenn Datei nicht existiert.
        """
        self.path = Path(path)
        # Überprüfen, ob die Config-Datei vorhanden ist
        if not self.path.is_file():
            raise FileNotFoundError(f"Config nicht gefunden: {self.path}")
        # Inhalte aus Datei laden
        self._load()

    def _load(self) -> None:
        """
        @brief Interne Methode: Liest TOML-Datei und setzt Config-Attribute.
        @raises KeyError falls Pflichtfelder (`handle`, `port`, `whoisport`) fehlen.
        """
        # Öffne Datei binär und parse mit tomllib
        with self.path.open('rb') as f:
            data = tomllib.load(f)

        try:
            # Pflichtfelder auslesen
            self.handle     = data['handle']
            port_list       = data['port']
            # Erzeuge Tupel (min, max) für Port-Range
            self.port_range = (int(port_list[0]), int(port_list[1]))
            self.whoisport  = int(data['whoisport'])
        except KeyError as e:
            # Fehlende Felder melden
            raise KeyError(f"Fehlendes Config-Feld: {e}")

        # Optional: Autoreply-Text laden, Standard leer
        self.autoreply = data.get('autoreply', '')
        # Bildverzeichnis aus Config oder Standard 'images'
        img_dir = data.get('imagepath', 'images')
        self.imagepath = Path(img_dir)
        # Verzeichnis anlegen, falls nicht vorhanden
        self.imagepath.mkdir(parents=True, exist_ok=True)

        # Zusätzliche Farben für Handles, falls in TOML definiert
        # Beispiel in alice.toml: [colors] Alice="RED"
        self.handle_colors: dict[str, str] = data.get('colors', {})

    def save(self) -> None:
        """
        @brief Speichert aktuelle Config-Attribute zurück in die TOML-Datei.
        """
        # Datenstruktur für TOML schreiben
        data = {
            'handle':    self.handle,
            'port':      list(self.port_range),
            'whoisport': self.whoisport,
            'autoreply': self.autoreply,
            'imagepath': str(self.imagepath),
            'colors':    self.handle_colors,
        }
        # Dump als TOML-Text
        toml_text = toml.dumps(data)
        # Überschreibe Datei mit UTF-8-Encoding
        with self.path.open('w', encoding='utf-8') as f:
            f.write(toml_text)
