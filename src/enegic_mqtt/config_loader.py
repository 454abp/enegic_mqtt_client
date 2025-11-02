import os
from pathlib import Path

import yaml

_ENV_TAG_REGISTERED = False


def load_config(path: str = "config.yaml"):
    """Load YAML config, resolve !ENV placeholders, allow overriding via ENEGIC_CONFIG_FILE."""

    def env_constructor(loader, node):
        value = loader.construct_scalar(node)
        env_var = value.strip("${} ")
        return os.getenv(env_var, "")

    global _ENV_TAG_REGISTERED
    if not _ENV_TAG_REGISTERED:
        yaml.SafeLoader.add_constructor("!ENV", env_constructor)
        _ENV_TAG_REGISTERED = True

    cfg_path = Path(os.getenv("ENEGIC_CONFIG_FILE", path)).expanduser()
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found at {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    return cfg or {}
