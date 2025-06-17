import tomllib
import toml
from pathlib import Path

class Config:
    """
    @file config.py
    @brief Lädt und speichert die TOML-Konfiguration für den Chat-Client.
    @details Enthält `handle`, `port_range`, `whoisport`, `autoreply`, `imagepath`.
    """

    def __init__(self, path: str):
        """
        @brief Konstruktor, lädt die Datei.
        @param[in] path Pfad zur TOML-Datei.
        """
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Config nicht gefunden: {self.path}")
        self._load()

    def _load(self) -> None:
        """
        @brief Interne Methode: Läd den TOML-Inhalt in Attribute.
        @throws KeyError falls Pflichtfelder fehlen.
        """
        with self.path.open('rb') as f:
            data = tomllib.load(f)

        try:
            self.handle     = data['handle']
            port_list       = data['port']
            self.port_range = (int(port_list[0]), int(port_list[1]))
            self.whoisport  = int(data['whoisport'])
        except KeyError as e:
            raise KeyError(f"Fehlendes Config-Feld: {e}")

        self.autoreply = data.get('autoreply', '')
        img_dir = data.get('imagepath', 'images')
        self.imagepath = Path(img_dir)
        self.imagepath.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """
        @brief Speichert aktuelle Werte zurück in die TOML-Datei.
        """
        data = {
            'handle':    self.handle,
            'port':      list(self.port_range),
            'whoisport': self.whoisport,
            'autoreply': self.autoreply,
            'imagepath': str(self.imagepath),
        }
        toml_text = toml.dumps(data)
        with self.path.open('w', encoding='utf-8') as f:
            f.write(toml_text)
