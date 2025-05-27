def load_config(path):
    import tomllib
    with open(path, 'rb') as f:
        return tomllib.load(f)
# Liest die Toml-Datei und gibt ein Discovery mit diesen Werten zuruck.
# So hat man in allen Modulen konsistent Zugriff auf dieselben Parameter.

