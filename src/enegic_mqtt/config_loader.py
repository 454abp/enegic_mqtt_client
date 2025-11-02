import os
import yaml

def load_config(path="config.yaml"):
    """Lädt YAML-Konfiguration und ersetzt !ENV-Platzhalter durch Environment-Variablen."""
    def env_constructor(loader, node):
        value = loader.construct_scalar(node)
        env_var = value.strip("${} ")
        return os.getenv(env_var, "")

    yaml.SafeLoader.add_constructor('!ENV', env_constructor)

    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}
