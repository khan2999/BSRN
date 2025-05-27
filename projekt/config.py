def load_config(path):
    import tomllib
    with open(path, 'rb') as f:
        return tomllib.load(f)

