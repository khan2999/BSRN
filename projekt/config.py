import tomllib
import toml
from pathlib import Path

class Config:
    """
    Lädt und verwaltet die TOML-Konfiguration für den Chat-Client.
    Attributes:
        handle: str                – eigener Nutzername
        port_range: tuple[int,int] – Portbereich für TCP/UDP-Server (inklusive)
        whoisport: int             – UDP-Port für Discovery JOIN/WHO/LEAVE
        autoreply: str             – optionaler Auto-Reply-Text
        imagepath: Path            – Verzeichnis für empfangene Bilder
    """
    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {self.path}")
        self._load()

    def _load(self) -> None:
        """
        @brief Interne Methode zum Einlesen und Verarbeiten der TOML-Datei.
        @raises KeyError Falls Pflichtfelder fehlen.
        """
        with self.path.open('rb') as f:
            data = tomllib.load(f)

        try:
            self.handle = data['handle']
            port_list = data['port']
            self.port_range = (int(port_list[0]), int(port_list[1]))
            self.whoisport = int(data['whoisport'])
        except KeyError as e:
            raise KeyError(f"Fehlendes Pflichtfeld in Config: {e}")

        self.autoreply = data.get('autoreply', '')
        img_dir = data.get('imagepath', 'images')
        self.imagepath = Path(img_dir)
        self.imagepath.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """
        @brief Schreibt aktuelle Konfiguration zurück in die TOML-Datei.
        """
        data = {
            'handle': self.handle,
            'port': list(self.port_range),
            'whoisport': self.whoisport,
            'autoreply': self.autoreply,
            'imagepath': str(self.imagepath),
        }
        toml_text = toml.dumps(data)
        with self.path.open('w', encoding='utf-8') as f:
            f.write(toml_text)
